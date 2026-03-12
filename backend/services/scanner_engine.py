"""Scanner engine — orchestrates the full scan pipeline.

Loads the scan from DB, runs each tool step in order, saves findings,
broadcasts progress via WebSocket, and handles stop/cancel signals.
"""

import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import select, update

from backend.database import async_session
from backend.models.scan import Scan, ScanStep, Finding
from backend.websocket.manager import ws_manager
from backend.services.tool_runners.base import BaseToolRunner, ToolFinding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool runner registry — populated at import time
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, BaseToolRunner] = {}


def _register_tools():
    """Import and register all available tool runners."""
    from backend.services.tool_runners.semgrep_runner import SemgrepRunner
    from backend.services.tool_runners.gitleaks_runner import GitleaksRunner
    from backend.services.tool_runners.trivy_runner import TrivyRunner
    from backend.services.tool_runners.npm_audit_runner import NpmAuditRunner
    from backend.services.tool_runners.eslint_runner import EslintRunner
    from backend.services.tool_runners.retirejs_runner import RetireJSRunner

    runners = [
        SemgrepRunner(),
        GitleaksRunner(),
        TrivyRunner(),
        NpmAuditRunner(),
        EslintRunner(),
        RetireJSRunner(),
    ]
    for runner in runners:
        TOOL_REGISTRY[runner.name] = runner


# Register on module load
_register_tools()

# ---------------------------------------------------------------------------
# Running scan tracking (for cancellation)
# ---------------------------------------------------------------------------

_running_scans: dict[int, bool] = {}  # scan_id -> should_stop


async def stop_scan(scan_id: int):
    """Signal a running scan to stop after the current step completes."""
    _running_scans[scan_id] = True
    logger.info("Stop signal sent for scan %d", scan_id)

    # Update DB status
    async with async_session() as session:
        await session.execute(
            update(Scan)
            .where(Scan.id == scan_id)
            .values(status="stopped", finished_at=datetime.utcnow())
        )
        await session.commit()

    await ws_manager.broadcast({
        "type": "scan_stopped",
        "scan_id": scan_id,
        "message": "Scan was stopped by user",
    })


def _should_stop(scan_id: int) -> bool:
    """Check if a scan has been signaled to stop."""
    return _running_scans.get(scan_id, False)


# ---------------------------------------------------------------------------
# Main pipeline execution
# ---------------------------------------------------------------------------

async def execute_pipeline(scan_id: int):
    """Run the full scan pipeline for a given scan ID.

    Steps:
    1. Load scan from DB, parse pipeline_json for ordered steps.
    2. For each step, run the corresponding tool or AI engine.
    3. Save findings to DB, broadcast progress.
    4. Handle errors per-step so one failure doesn't kill the pipeline.
    5. Mark scan as completed (or stopped/failed).
    """
    _running_scans[scan_id] = False

    async with async_session() as session:
        # Load the scan
        result = await session.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalars().first()

        if not scan:
            logger.error("Scan %d not found", scan_id)
            return

        # Update scan to running
        scan.status = "running"
        scan.started_at = datetime.utcnow()
        await session.commit()

        # Load project to get repo_path
        from backend.models.project import Project
        proj_result = await session.execute(
            select(Project).where(Project.id == scan.project_id)
        )
        project = proj_result.scalars().first()
        if not project:
            logger.error("Project %d not found for scan %d", scan.project_id, scan_id)
            scan.status = "failed"
            scan.finished_at = datetime.utcnow()
            await session.commit()
            return

        repo_path = project.repo_path

    # Parse pipeline steps
    try:
        pipeline_steps = json.loads(scan.pipeline_json) if scan.pipeline_json else []
    except json.JSONDecodeError:
        logger.error("Invalid pipeline_json for scan %d", scan_id)
        pipeline_steps = []

    if not pipeline_steps:
        # Default pipeline based on scan mode
        pipeline_steps = _build_default_pipeline(scan.mode)

    # Collect step names for the frontend pipeline panel
    step_names = []
    for step_def in pipeline_steps:
        if isinstance(step_def, str):
            step_names.append(step_def)
        else:
            step_names.append(step_def.get("tool", step_def.get("tool_name", "unknown")))

    # Broadcast scan started — include step_names so UI can build the pipeline steps panel
    await ws_manager.broadcast({
        "type": "scan_started",
        "scan_id": scan_id,
        "total_steps": len(pipeline_steps),
        "step_names": step_names,
    })

    total_findings = 0
    total_tokens = 0
    total_cost = 0.0

    # Load existing ScanStep records (created by the router) or create new ones
    step_records: list[int] = []
    async with async_session() as session:
        result = await session.execute(
            select(ScanStep)
            .where(ScanStep.scan_id == scan_id)
            .order_by(ScanStep.step_order)
        )
        existing_steps = result.scalars().all()

        if existing_steps and len(existing_steps) == len(pipeline_steps):
            # Re-use step records already created by the scan router
            step_records = [s.id for s in existing_steps]
        else:
            # Fallback: create step records if none exist yet
            for idx, step_def in enumerate(pipeline_steps):
                tool_name = step_def if isinstance(step_def, str) else step_def.get("tool", "unknown")
                step = ScanStep(
                    scan_id=scan_id,
                    step_order=idx + 1,
                    tool_name=tool_name,
                    status="pending",
                )
                session.add(step)
                await session.flush()
                step_records.append(step.id)
            await session.commit()

    # Execute each step
    for idx, step_def in enumerate(pipeline_steps):
        step_id = step_records[idx]

        # Parse step definition
        if isinstance(step_def, str):
            tool_name = step_def
            step_config = {}
        else:
            tool_name = step_def.get("tool", "unknown")
            step_config = step_def.get("config", {})

        # Check for stop signal
        if _should_stop(scan_id):
            logger.info("Scan %d stopped before step %s", scan_id, tool_name)
            await _update_step_status(step_id, "skipped")
            continue

        logger.info("Scan %d: running step %d/%d — %s", scan_id, idx + 1, len(pipeline_steps), tool_name)

        # Update step to running
        await _update_step_status(step_id, "running", started_at=datetime.utcnow())

        # Broadcast step progress
        await ws_manager.send_scan_progress(
            scan_id=scan_id,
            step_name=tool_name,
            status="running",
            files_processed=idx,
            total_files=len(pipeline_steps),
            tokens_used=total_tokens,
            cost_usd=total_cost,
            findings_count=total_findings,
            message=f"Running {tool_name}...",
        )

        step_findings: list[ToolFinding] = []
        step_error: str | None = None

        try:
            if tool_name == "ai_analysis":
                # AI analysis step — delegate to ai_engine
                # Pass scan mode so ai_engine can apply smart hybrid logic
                step_config_with_mode = {**step_config, "mode": scan.mode}
                step_findings, tokens, cost = await _run_ai_step(
                    scan_id, step_id, repo_path, scan.branch, step_config_with_mode
                )
                total_tokens += tokens
                total_cost += cost
            else:
                # Tool runner step
                runner = TOOL_REGISTRY.get(tool_name)
                if runner is None:
                    logger.warning("Unknown tool: %s — skipping", tool_name)
                    step_error = f"Unknown tool: {tool_name}"
                elif not await runner.is_installed():
                    logger.warning("Tool %s is not installed — skipping", tool_name)
                    step_error = f"{tool_name} is not installed"
                else:
                    # Build on_progress callback that broadcasts step_status over WS
                    async def _on_tool_progress(msg: str, count: int, _scan_id=scan_id, _tool=tool_name):
                        await ws_manager.broadcast({
                            "type": "step_status",
                            "scan_id": _scan_id,
                            "step_name": _tool,
                            "message": msg,
                            "interim_count": count,
                        })

                    step_findings = await runner.run(repo_path, config=step_config, on_progress=_on_tool_progress)

        except Exception as exc:
            logger.exception("Error running step %s for scan %d: %s", tool_name, scan_id, exc)
            step_error = str(exc)

        # Save findings to DB
        if step_findings:
            await _save_findings(step_findings, scan_id, step_id)
            total_findings += len(step_findings)

            # Broadcast each finding in real-time
            for f in step_findings:
                await ws_manager.send_finding(scan_id, {
                    "title": f.title,
                    "severity": f.severity,
                    "type": f.type,
                    "file_path": f.file_path,
                    "tool_name": f.tool_name,
                    "line_start": f.line_start,
                })

        # Update step status
        step_status = "failed" if step_error else "completed"
        if _should_stop(scan_id) and step_error is None:
            step_status = "completed"

        await _update_step_status(
            step_id,
            step_status,
            finished_at=datetime.utcnow(),
            findings_count=len(step_findings),
            error_message=step_error,
        )

        # Broadcast step_complete — lets the UI update findings count per tool
        await ws_manager.broadcast({
            "type": "step_complete",
            "scan_id": scan_id,
            "step_name": tool_name,
            "status": step_status,
            "findings_count": len(step_findings),
            "error": step_error,
        })

        # Broadcast overall progress
        await ws_manager.send_scan_progress(
            scan_id=scan_id,
            step_name=tool_name,
            status=step_status,
            files_processed=idx + 1,
            total_files=len(pipeline_steps),
            tokens_used=total_tokens,
            cost_usd=total_cost,
            findings_count=total_findings,
            message=f"{tool_name} {step_status}" + (f": {step_error}" if step_error else ""),
        )

    # Finalize scan
    final_status = "stopped" if _should_stop(scan_id) else "completed"
    async with async_session() as session:
        await session.execute(
            update(Scan)
            .where(Scan.id == scan_id)
            .values(
                status=final_status,
                finished_at=datetime.utcnow(),
                tokens_used=total_tokens,
                cost_usd=total_cost,
            )
        )
        await session.commit()

    # Broadcast scan completion
    await ws_manager.send_scan_complete(scan_id, {
        "status": final_status,
        "total_findings": total_findings,
        "total_steps": len(pipeline_steps),
        "tokens_used": total_tokens,
        "cost_usd": total_cost,
    })

    # Clean up tracking
    _running_scans.pop(scan_id, None)
    logger.info("Scan %d finished with status=%s, findings=%d", scan_id, final_status, total_findings)


# ---------------------------------------------------------------------------
# Helper: default pipeline builder
# ---------------------------------------------------------------------------

def _build_default_pipeline(mode: str) -> list[str]:
    """Build default pipeline steps based on scan mode."""
    tool_steps = ["semgrep", "gitleaks", "trivy", "npm_audit", "eslint_security", "retirejs"]
    ai_steps = ["ai_analysis"]

    if mode == "tools_only":
        return tool_steps
    elif mode == "ai_only":
        return ai_steps
    else:
        # hybrid mode — run tools first, then AI
        return tool_steps + ai_steps


# ---------------------------------------------------------------------------
# Helper: run AI analysis step
# ---------------------------------------------------------------------------

async def _run_ai_step(
    scan_id: int,
    step_id: int,
    repo_path: str,
    branch: str,
    config: dict,
) -> tuple[list[ToolFinding], int, float]:
    """Run the AI analysis step. Returns (findings, tokens_used, cost_usd)."""
    try:
        from backend.services.ai_engine import run_ai_analysis
        return await run_ai_analysis(
            scan_id=scan_id,
            step_id=step_id,
            repo_path=repo_path,
            branch=branch,
            config=config,
        )
    except ImportError:
        logger.warning("AI engine not yet implemented — skipping AI analysis step")
        return [], 0, 0.0
    except Exception as exc:
        logger.exception("AI analysis failed: %s", exc)
        return [], 0, 0.0


# ---------------------------------------------------------------------------
# Helper: save findings to DB
# ---------------------------------------------------------------------------

async def _save_findings(findings: list[ToolFinding], scan_id: int, step_id: int):
    """Convert ToolFinding objects to DB Finding records and persist."""
    async with async_session() as session:
        for f in findings:
            db_finding = Finding(
                scan_id=scan_id,
                scan_step_id=step_id,
                type=f.type,
                severity=f.severity,
                title=f.title,
                description=f.description,
                file_path=f.file_path,
                line_start=f.line_start,
                line_end=f.line_end,
                code_snippet=f.code_snippet,
                tool_name=f.tool_name,
                confidence=f.confidence,
                cwe_id=f.cwe_id,
                recommendation=f.recommendation,
                status="open",
            )
            session.add(db_finding)
        await session.commit()


# ---------------------------------------------------------------------------
# Helper: update step status
# ---------------------------------------------------------------------------

async def _update_step_status(
    step_id: int,
    status: str,
    started_at: datetime = None,
    finished_at: datetime = None,
    findings_count: int = None,
    error_message: str = None,
    tokens_used: int = None,
):
    """Update a ScanStep record in the database."""
    values: dict = {"status": status}
    if started_at is not None:
        values["started_at"] = started_at
    if finished_at is not None:
        values["finished_at"] = finished_at
    if findings_count is not None:
        values["findings_count"] = findings_count
    if error_message is not None:
        values["error_message"] = error_message
    if tokens_used is not None:
        values["tokens_used"] = tokens_used

    async with async_session() as session:
        await session.execute(
            update(ScanStep)
            .where(ScanStep.id == step_id)
            .values(**values)
        )
        await session.commit()

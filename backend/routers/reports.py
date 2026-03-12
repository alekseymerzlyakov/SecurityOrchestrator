"""Reports router — scan history and report generation/download."""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.config import REPORTS_DIR
from backend.models.project import Project
from backend.models.scan import Scan, ScanStep, Finding, TokenUsage

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ScanHistoryItem(BaseModel):
    id: int
    project_id: int
    project_name: Optional[str] = None
    branch: str
    status: str
    mode: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    total_files: int = 0
    files_processed: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    findings_count: int = 0
    critical_count: int = 0
    high_count: int = 0

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    format: str = "json"  # json / html / pdf
    report_type: str = "technical"  # executive / technical


class ReportOut(BaseModel):
    scan_id: int
    format: str
    report_type: str
    generated_at: str
    data: Dict[str, Any]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/scans", response_model=List[ScanHistoryItem])
async def list_scan_history(
    project_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List scan history with summary information."""
    stmt = select(Scan).order_by(Scan.started_at.desc())
    if project_id is not None:
        stmt = stmt.where(Scan.project_id == project_id)

    result = await db.execute(stmt)
    scans = result.scalars().all()

    items = []
    for scan in scans:
        # Get project name
        proj_result = await db.execute(
            select(Project.name).where(Project.id == scan.project_id)
        )
        project_name = proj_result.scalar()

        # Get finding counts
        total_q = select(func.count(Finding.id)).where(Finding.scan_id == scan.id)
        total_result = await db.execute(total_q)
        findings_count = total_result.scalar() or 0

        crit_q = select(func.count(Finding.id)).where(
            Finding.scan_id == scan.id, Finding.severity == "critical"
        )
        crit_result = await db.execute(crit_q)
        critical_count = crit_result.scalar() or 0

        high_q = select(func.count(Finding.id)).where(
            Finding.scan_id == scan.id, Finding.severity == "high"
        )
        high_result = await db.execute(high_q)
        high_count = high_result.scalar() or 0

        items.append(ScanHistoryItem(
            id=scan.id,
            project_id=scan.project_id,
            project_name=project_name,
            branch=scan.branch,
            status=scan.status,
            mode=scan.mode,
            started_at=scan.started_at,
            finished_at=scan.finished_at,
            total_files=scan.total_files,
            files_processed=scan.files_processed,
            tokens_used=scan.tokens_used,
            cost_usd=scan.cost_usd,
            findings_count=findings_count,
            critical_count=critical_count,
            high_count=high_count,
        ))

    return items


@router.post("/{scan_id}/generate", response_model=ReportOut)
async def generate_report(
    scan_id: int,
    payload: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a report for a scan.

    Currently returns scan data as JSON. PDF/HTML generation
    will be added in Phase 5 via the report_generator service.
    """
    # Validate scan exists
    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = scan_result.scalars().first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Get project
    proj_result = await db.execute(
        select(Project).where(Project.id == scan.project_id)
    )
    project = proj_result.scalars().first()

    # Get steps
    steps_result = await db.execute(
        select(ScanStep).where(ScanStep.scan_id == scan_id).order_by(ScanStep.step_order)
    )
    steps = steps_result.scalars().all()

    # Get findings
    findings_result = await db.execute(
        select(Finding).where(Finding.scan_id == scan_id).order_by(Finding.severity)
    )
    findings = findings_result.scalars().all()

    # Get token usage
    tokens_result = await db.execute(
        select(TokenUsage).where(TokenUsage.scan_id == scan_id)
    )
    token_records = tokens_result.scalars().all()

    # Build severity summary
    severity_counts: Dict[str, int] = {}
    for f in findings:
        sev = f.severity or "unknown"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Build report data
    report_data: Dict[str, Any] = {
        "scan": {
            "id": scan.id,
            "project_name": project.name if project else None,
            "repo_path": project.repo_path if project else None,
            "branch": scan.branch,
            "status": scan.status,
            "mode": scan.mode,
            "started_at": str(scan.started_at) if scan.started_at else None,
            "finished_at": str(scan.finished_at) if scan.finished_at else None,
            "total_files": scan.total_files,
            "files_processed": scan.files_processed,
            "tokens_used": scan.tokens_used,
            "cost_usd": scan.cost_usd,
        },
        "summary": {
            "total_findings": len(findings),
            "severity_counts": severity_counts,
        },
        "steps": [
            {
                "step_order": s.step_order,
                "tool_name": s.tool_name,
                "status": s.status,
                "findings_count": s.findings_count,
                "tokens_used": s.tokens_used,
                "error_message": s.error_message,
            }
            for s in steps
        ],
        "findings": [
            {
                "id": f.id,
                "type": f.type,
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "file_path": f.file_path,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "code_snippet": f.code_snippet,
                "tool_name": f.tool_name,
                "confidence": f.confidence,
                "cvss_score": f.cvss_score,
                "cwe_id": f.cwe_id,
                "recommendation": f.recommendation,
                "status": f.status,
            }
            for f in findings
        ],
        "token_usage": [
            {
                "input_tokens": t.input_tokens,
                "output_tokens": t.output_tokens,
                "cost_usd": t.cost_usd,
                "chunk_description": t.chunk_description,
            }
            for t in token_records
        ],
    }

    # For executive reports, reduce detail
    if payload.report_type == "executive":
        report_data.pop("token_usage", None)
        # Simplify findings to just summary
        report_data["findings"] = [
            {
                "severity": f.severity,
                "title": f.title,
                "file_path": f.file_path,
                "status": f.status,
                "recommendation": f.recommendation,
            }
            for f in findings
        ]

    # For non-JSON formats, generate the file via report_generator service
    if payload.format in ("html", "pdf"):
        try:
            from backend.services.report_generator import generate_report as gen_report
            file_path = await gen_report(
                scan_id=scan_id,
                format=payload.format,
                report_type=payload.report_type,
            )
            # Build a download URL for the generated file
            download_url = f"/api/reports/{scan_id}/download/{payload.format}"
            report_data["download_url"] = download_url
            report_data["file_path"] = str(file_path)
        except Exception as exc:
            logger.error("Report generation failed: %s", exc)
            report_data["note"] = f"Report generation error: {str(exc)}"

    return ReportOut(
        scan_id=scan_id,
        format=payload.format,
        report_type=payload.report_type,
        generated_at=datetime.utcnow().isoformat(),
        data=report_data,
    )


@router.get("/{scan_id}/download/{format}")
async def download_report(
    scan_id: int,
    format: str,
    db: AsyncSession = Depends(get_db),
):
    """Download a generated report.

    For JSON, returns the data directly. For HTML/PDF, serves the
    generated file when available (Phase 5).
    """
    if format not in ("json", "html", "pdf"):
        raise HTTPException(status_code=400, detail="Format must be json, html, or pdf")

    # Verify scan exists
    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = scan_result.scalars().first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if format == "json":
        # Generate and return JSON inline
        payload = ReportGenerateRequest(format="json", report_type="technical")
        report = await generate_report(scan_id, payload, db)
        return JSONResponse(
            content=report.data,
            headers={
                "Content-Disposition": f'attachment; filename="scan_{scan_id}_report.json"'
            },
        )

    # For HTML/PDF, check if a pre-generated file exists
    from pathlib import Path
    # Try both naming conventions
    for report_type_suffix in ["technical", "executive"]:
        report_file = REPORTS_DIR / f"scan_{scan_id}_{report_type_suffix}.{format}"
        if report_file.exists():
            from fastapi.responses import FileResponse
            media_type = "text/html" if format == "html" else "application/pdf"
            return FileResponse(
                path=str(report_file),
                media_type=media_type,
                filename=f"scan_{scan_id}_report.{format}",
            )

    # Also try without report_type suffix
    report_file = REPORTS_DIR / f"scan_{scan_id}.{format}"
    if report_file.exists():
        from fastapi.responses import FileResponse
        media_type = "text/html" if format == "html" else "application/pdf"
        return FileResponse(
            path=str(report_file),
            media_type=media_type,
            filename=f"scan_{scan_id}_report.{format}",
        )

    raise HTTPException(
        status_code=404,
        detail=f"{format.upper()} report not generated yet. Use POST /{scan_id}/generate first.",
    )


@router.get("/{scan_id}/view", response_class=HTMLResponse)
async def view_report_online(
    scan_id: int,
    report_type: str = "technical",
    db: AsyncSession = Depends(get_db),
):
    """Render an HTML report inline in the browser (no download).

    Returns the full HTML report for online viewing.
    Query param: report_type=technical|executive
    """
    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = scan_result.scalars().first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    try:
        from backend.services.report_generator import generate_report as gen_report, _load_report_data, _generate_html
        import tempfile, os

        data = await _load_report_data(scan_id)
        if not data:
            raise HTTPException(status_code=404, detail="No report data found")

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as tmp:
            tmp_path = tmp.name

        _generate_html(data, tmp_path, report_type)
        with open(tmp_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        os.unlink(tmp_path)
        return HTMLResponse(content=html_content)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("View report error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


class SummarizeOut(BaseModel):
    scan_id: int
    summary: str
    model_used: str
    prompt_name: str
    generated_at: str
    cached: bool = False  # True if returned from DB cache


@router.get("/{scan_id}/summary", response_model=SummarizeOut)
async def get_cached_summary(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return cached AI summary for a scan if it exists, else 404."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalars().first()
    if not scan or not scan.ai_summary:
        raise HTTPException(status_code=404, detail="No cached summary")
    return SummarizeOut(
        scan_id=scan_id,
        summary=scan.ai_summary,
        model_used="",
        prompt_name="cached",
        generated_at=scan.ai_summary_at.isoformat() if scan.ai_summary_at else "",
        cached=True,
    )


@router.post("/{scan_id}/summarize", response_model=SummarizeOut)
async def summarize_report(
    scan_id: int,
    regenerate: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI executive summary for a scan report.

    Uses the 'Report: AI Executive Summary' prompt and the first available
    AI model configured in Settings. Returns Markdown text.
    Saves result to DB — subsequent calls return cached version unless regenerate=True.
    """
    from backend.services.report_generator import _load_report_data
    from backend.models.settings import AIModel, AIProvider
    from backend.models.prompt import Prompt
    from backend.services.ai_engine import get_provider

    # Return cached summary if available and not forced to regenerate
    if not regenerate:
        scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan_cached = scan_result.scalars().first()
        if scan_cached and scan_cached.ai_summary:
            logger.info("Returning cached summary for scan %d", scan_id)
            return SummarizeOut(
                scan_id=scan_id,
                summary=scan_cached.ai_summary,
                model_used="",
                prompt_name="cached",
                generated_at=scan_cached.ai_summary_at.isoformat() if scan_cached.ai_summary_at else "",
                cached=True,
            )

    # Load report data
    data = await _load_report_data(scan_id)
    if not data:
        raise HTTPException(status_code=404, detail="Scan not found or has no data")

    # Load the summary prompt from DB (by name)
    prompt_result = await db.execute(
        select(Prompt).where(Prompt.name == "Report: AI Executive Summary")
    )
    prompt_record = prompt_result.scalars().first()

    if not prompt_record:
        # Fallback: load directly from file
        from backend.config import PROMPTS_DIR
        prompt_file = PROMPTS_DIR / "report_summary.txt"
        if prompt_file.exists():
            prompt_content = prompt_file.read_text(encoding="utf-8")
            prompt_name = "report_summary.txt (file fallback)"
        else:
            raise HTTPException(
                status_code=404,
                detail="Summary prompt not found. Restart backend to seed built-in prompts."
            )
    else:
        prompt_content = prompt_record.content
        prompt_name = prompt_record.name

    # Get first active AI model
    model_result = await db.execute(select(AIModel).where(AIModel.is_active == True))
    model = model_result.scalars().first()
    if not model:
        raise HTTPException(
            status_code=400,
            detail="No AI model configured. Add one in Settings → AI Models."
        )

    provider_result = await db.execute(
        select(AIProvider).where(AIProvider.id == model.provider_id)
    )
    provider_record = provider_result.scalars().first()
    if not provider_record:
        raise HTTPException(status_code=400, detail="AI provider not found")

    # Build compact scan data for the prompt (avoid huge code snippets)
    compact_data = {
        "project": data["project"],
        "scan": data["scan"],
        "summary": data["summary"],
        "steps": data["steps"],
        "top_findings": [
            {
                "severity": f["severity"],
                "title": f["title"],
                "type": f.get("type"),
                "file_path": f.get("file_path"),
                "cwe_id": f.get("cwe_id"),
                "description": (f.get("description") or "")[:300],
                "recommendation": (f.get("recommendation") or "")[:200],
                "tool_name": f.get("tool_name"),
            }
            for f in data["findings"]
        ],
    }

    # Build the user message — replace placeholder with actual data
    user_message = prompt_content.replace(
        "[SCAN_DATA_JSON]",
        json.dumps(compact_data, ensure_ascii=False, indent=2, default=str)
    )

    # Decrypt API key (stored encrypted in DB, just like ai_engine.py does)
    from backend.config import decrypt_value
    api_key = None
    if provider_record.api_key:
        try:
            api_key = decrypt_value(provider_record.api_key)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Не удалось расшифровать API ключ. Пересохраните ключ в Settings → AI Providers."
            )

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="API ключ не задан. Добавьте ключ в Settings → AI Providers."
        )

    # Call AI — pass credentials directly to analyze() (no configure() method)
    try:
        provider = get_provider(provider_record.provider_type)
        response = await provider.analyze(
            system_prompt="You are a senior security engineer writing professional executive security reports.",
            user_prompt=user_message,
            model_id=model.model_id,
            api_key=api_key,
            base_url=provider_record.base_url or None,
            max_output_tokens=4096,
        )
        summary_text = response.content
        # Save to DB so next call returns cached version
        generated_at = datetime.utcnow()
        await db.execute(
            update(Scan).where(Scan.id == scan_id).values(
                ai_summary=summary_text,
                ai_summary_at=generated_at,
            )
        )
        await db.commit()
        logger.info("Saved AI summary for scan %d (%d chars)", scan_id, len(summary_text))
    except Exception as exc:
        logger.error("AI summary failed type=%s repr=%r str=%s", type(exc).__name__, exc, exc)
        err_msg = str(exc)
        err_lower = err_msg.lower()
        # Credit / billing errors (400 from Anthropic)
        if "credit balance" in err_lower or "too low" in err_lower or "billing" in err_lower or "quota" in err_lower or "plans & billing" in err_lower:
            raise HTTPException(status_code=402,
                detail="Недостаточно кредитов на аккаунте AI провайдера. Пополните баланс на console.anthropic.com/settings/billing")
        # Auth errors
        if "401" in err_msg or "authentication" in err_lower or "invalid api key" in err_lower or "api_key" in err_lower:
            raise HTTPException(status_code=400,
                detail="Неверный API ключ. Проверьте ключ в Settings → AI Providers.")
        # Rate limit
        if "rate limit" in err_lower or "429" in err_msg:
            raise HTTPException(status_code=429,
                detail="Rate limit Anthropic API — система автоматически повторила запрос 4 раза с паузами до 60с, но лимит не сбросился. "
                       "Подождите 1–2 минуты и запустите скан заново. "
                       "Или перейдите на более медленную модель (Haiku) — у неё выше лимиты.")
        # Connection errors
        if "connection" in err_lower or "connect" in err_lower or "timeout" in err_lower:
            raise HTTPException(status_code=503,
                detail="Нет соединения с AI провайдером. Проверьте интернет-соединение и доступность API.")
        raise HTTPException(status_code=500, detail=f"AI call failed: {exc}")

    return SummarizeOut(
        scan_id=scan_id,
        summary=summary_text,
        model_used=model.model_id,
        prompt_name=prompt_name,
        generated_at=generated_at.isoformat(),
        cached=False,
    )

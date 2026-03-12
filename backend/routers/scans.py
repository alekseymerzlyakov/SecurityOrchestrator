"""Scans router — start, list, monitor, and stop security scans."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, async_session
from backend.models.project import Project
from backend.models.scan import Scan, ScanStep, TokenUsage

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory registry of running scan tasks so we can cancel them.
_running_tasks: dict[int, asyncio.Task] = {}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ScanCreate(BaseModel):
    project_id: int
    branch: str
    mode: str = "hybrid"  # hybrid / tools_only / ai_only
    pipeline_json: Optional[str] = None  # JSON array of tool names / step defs


class ScanStepOut(BaseModel):
    id: int
    scan_id: int
    step_order: int
    tool_name: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    files_processed: int = 0
    findings_count: int = 0
    tokens_used: int = 0
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class ScanOut(BaseModel):
    id: int
    project_id: int
    branch: str
    status: str
    mode: str
    pipeline_json: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    total_files: int = 0
    files_processed: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    estimated_total_tokens: Optional[int] = None
    estimated_total_cost: Optional[float] = None

    model_config = {"from_attributes": True}


class ScanDetailOut(ScanOut):
    steps: List[ScanStepOut] = []


class ScanProgressOut(BaseModel):
    scan_id: int
    status: str
    files_processed: int
    total_files: int
    tokens_used: int
    cost_usd: float
    estimated_total_tokens: Optional[int] = None
    estimated_total_cost: Optional[float] = None
    percent_complete: float = 0.0
    current_step: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class EstimateRequest(BaseModel):
    project_id: int
    model_id: Optional[int] = None  # if None, return all models from DB


class ModelCostEstimate(BaseModel):
    model_name: str
    model_id: str
    provider: str
    total_files: int
    total_code_tokens: int
    estimated_chunks: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_cost_usd: float
    input_price_per_mtok: float
    output_price_per_mtok: float
    within_budget: bool
    max_budget_usd: float


class EstimateResponse(BaseModel):
    project_id: int
    repo_path: str
    total_files: int
    total_code_tokens: int
    models: List[ModelCostEstimate]


@router.post("/estimate", response_model=EstimateResponse)
async def estimate_scan_cost(payload: EstimateRequest, db: AsyncSession = Depends(get_db)):
    """Estimate token usage and cost for an AI scan without running it.

    Returns a per-model breakdown showing how many tokens the full repo
    would consume and what it would cost on each configured model.
    """
    from backend.models.settings import AIModel, AIProvider
    from backend.services.token_tracker import estimate_scan_cost as _estimate

    # Verify project
    proj_result = await db.execute(select(Project).where(Project.id == payload.project_id))
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Load models
    if payload.model_id:
        models_result = await db.execute(
            select(AIModel).where(AIModel.id == payload.model_id)
        )
        models = models_result.scalars().all()
    else:
        models_result = await db.execute(select(AIModel))
        models = models_result.scalars().all()

    if not models:
        raise HTTPException(status_code=404, detail="No AI models configured. Add a model in Settings → AI Models.")

    # Load providers for names
    providers_result = await db.execute(select(AIProvider))
    providers = {p.id: p for p in providers_result.scalars().all()}

    # Run estimation once (same repo for all models)
    first_model = models[0]
    base_estimate = await _estimate(
        repo_path=project.repo_path,
        model={
            "input_price_per_mtok": first_model.input_price_per_mtok or 0.0,
            "output_price_per_mtok": first_model.output_price_per_mtok or 0.0,
            "context_window": first_model.context_window or 200000,
            "max_tokens_per_run": first_model.max_tokens_per_run or 1_000_000,
            "max_budget_usd": first_model.max_budget_usd or 50.0,
        },
    )

    total_files = base_estimate["total_files"]
    total_code_tokens = base_estimate["total_code_tokens"]
    estimated_chunks = base_estimate["estimated_chunks"]

    model_estimates: list[ModelCostEstimate] = []
    for m in models:
        provider = providers.get(m.provider_id)
        inp_price = m.input_price_per_mtok or 0.0
        out_price = m.output_price_per_mtok or 0.0
        max_budget = m.max_budget_usd or 50.0

        # Re-calculate cost for this model's pricing
        inp_tokens = base_estimate["estimated_input_tokens"]
        out_tokens = base_estimate["estimated_output_tokens"]
        inp_cost = (inp_tokens / 1_000_000) * inp_price
        out_cost = (out_tokens / 1_000_000) * out_price
        total_cost = round(inp_cost + out_cost, 4)

        model_estimates.append(ModelCostEstimate(
            model_name=m.name,
            model_id=m.model_id,
            provider=provider.name if provider else "unknown",
            total_files=total_files,
            total_code_tokens=total_code_tokens,
            estimated_chunks=estimated_chunks,
            estimated_input_tokens=inp_tokens,
            estimated_output_tokens=out_tokens,
            estimated_total_cost_usd=total_cost,
            input_price_per_mtok=inp_price,
            output_price_per_mtok=out_price,
            within_budget=total_cost <= max_budget,
            max_budget_usd=max_budget,
        ))

    # Sort cheapest first
    model_estimates.sort(key=lambda x: x.estimated_total_cost_usd)

    return EstimateResponse(
        project_id=project.id,
        repo_path=project.repo_path,
        total_files=total_files,
        total_code_tokens=total_code_tokens,
        models=model_estimates,
    )


@router.post("/", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def start_scan(payload: ScanCreate, db: AsyncSession = Depends(get_db)):
    """Start a new security scan."""
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == payload.project_id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Parse pipeline (or use default)
    pipeline = None
    if payload.pipeline_json:
        try:
            pipeline = json.loads(payload.pipeline_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid pipeline_json")
    else:
        # Default pipeline order
        pipeline = [
            {"tool_name": "semgrep"},
            {"tool_name": "gitleaks"},
            {"tool_name": "trivy"},
            {"tool_name": "npm_audit"},
            {"tool_name": "ai_analysis"},
        ]

    # Create scan record
    scan = Scan(
        project_id=payload.project_id,
        branch=payload.branch,
        mode=payload.mode,
        status="pending",
        pipeline_json=json.dumps(pipeline),
        started_at=datetime.utcnow(),
    )
    db.add(scan)
    await db.flush()  # get scan.id before creating steps

    # Create scan step records
    for idx, step_def in enumerate(pipeline):
        tool_name = step_def if isinstance(step_def, str) else step_def.get("tool_name", f"step_{idx}")
        step = ScanStep(
            scan_id=scan.id,
            step_order=idx,
            tool_name=tool_name,
            status="pending",
        )
        db.add(step)

    await db.commit()
    await db.refresh(scan)

    # Launch pipeline execution as a background task
    async def _run_pipeline(scan_id: int):
        try:
            from backend.services.scanner_engine import execute_pipeline
            await execute_pipeline(scan_id)
        except Exception as exc:
            logger.error("Pipeline execution failed for scan %s: %s", scan_id, exc)
            async with async_session() as s:
                await s.execute(
                    update(Scan)
                    .where(Scan.id == scan_id)
                    .values(status="failed", finished_at=datetime.utcnow())
                )
                await s.commit()
        finally:
            _running_tasks.pop(scan_id, None)

    task = asyncio.create_task(_run_pipeline(scan.id))
    _running_tasks[scan.id] = task

    return scan


@router.get("/", response_model=List[ScanOut])
async def list_scans(
    project_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List scans, optionally filtered by project_id."""
    stmt = select(Scan).order_by(Scan.started_at.desc())
    if project_id is not None:
        stmt = stmt.where(Scan.project_id == project_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{scan_id}", response_model=ScanDetailOut)
async def get_scan(scan_id: int, db: AsyncSession = Depends(get_db)):
    """Get scan details including steps."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalars().first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    steps_result = await db.execute(
        select(ScanStep).where(ScanStep.scan_id == scan_id).order_by(ScanStep.step_order)
    )
    steps = steps_result.scalars().all()

    return ScanDetailOut(
        **{c.name: getattr(scan, c.name) for c in scan.__table__.columns},
        steps=[ScanStepOut.model_validate(s) for s in steps],
    )


@router.get("/{scan_id}/progress", response_model=ScanProgressOut)
async def get_scan_progress(scan_id: int, db: AsyncSession = Depends(get_db)):
    """Get real-time progress for a running scan."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalars().first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Determine current step
    steps_result = await db.execute(
        select(ScanStep)
        .where(ScanStep.scan_id == scan_id)
        .order_by(ScanStep.step_order)
    )
    steps = steps_result.scalars().all()
    current_step = None
    for step in steps:
        if step.status == "running":
            current_step = step.tool_name
            break

    percent = 0.0
    if scan.total_files and scan.total_files > 0:
        percent = round((scan.files_processed / scan.total_files) * 100, 2)

    return ScanProgressOut(
        scan_id=scan.id,
        status=scan.status,
        files_processed=scan.files_processed,
        total_files=scan.total_files,
        tokens_used=scan.tokens_used,
        cost_usd=scan.cost_usd,
        estimated_total_tokens=scan.estimated_total_tokens,
        estimated_total_cost=scan.estimated_total_cost,
        percent_complete=percent,
        current_step=current_step,
    )


@router.post("/{scan_id}/stop", status_code=status.HTTP_200_OK)
async def stop_scan(scan_id: int, db: AsyncSession = Depends(get_db)):
    """Stop a running scan."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalars().first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"Scan is already {scan.status}")

    # Cancel the background task if it exists
    task = _running_tasks.pop(scan_id, None)
    if task and not task.done():
        task.cancel()

    # Update scan and running steps
    await db.execute(
        update(Scan)
        .where(Scan.id == scan_id)
        .values(status="stopped", finished_at=datetime.utcnow())
    )
    await db.execute(
        update(ScanStep)
        .where(ScanStep.scan_id == scan_id, ScanStep.status.in_(["pending", "running"]))
        .values(status="skipped")
    )
    await db.commit()

    return {"message": "Scan stopped", "scan_id": scan_id}


@router.get("/{scan_id}/steps", response_model=List[ScanStepOut])
async def get_scan_steps(scan_id: int, db: AsyncSession = Depends(get_db)):
    """Get all steps for a scan."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Scan not found")

    steps_result = await db.execute(
        select(ScanStep)
        .where(ScanStep.scan_id == scan_id)
        .order_by(ScanStep.step_order)
    )
    return steps_result.scalars().all()

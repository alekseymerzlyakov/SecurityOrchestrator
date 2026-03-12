"""Findings router — query, update, and summarize security findings."""

import logging
from datetime import datetime
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.scan import Finding

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class FindingOut(BaseModel):
    id: int
    scan_id: int
    scan_step_id: Optional[int] = None
    type: Optional[str] = None
    severity: Optional[str] = None
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    code_snippet: Optional[str] = None
    tool_name: Optional[str] = None
    confidence: Optional[str] = None
    cvss_score: Optional[float] = None
    cwe_id: Optional[str] = None
    recommendation: Optional[str] = None
    commit_author: Optional[str] = None
    commit_date: Optional[str] = None
    status: str = "open"
    jira_ticket_id: Optional[str] = None
    jira_ticket_url: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FindingStatusUpdate(BaseModel):
    status: str  # open / in_progress / fixed / false_positive


class FindingSummaryOut(BaseModel):
    total: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    by_status: Dict[str, int] = {}
    by_tool: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=FindingSummaryOut)
async def get_findings_summary(
    scan_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated summary counts of findings by severity, status, and tool."""
    base = select(Finding)
    if scan_id is not None:
        base = base.where(Finding.scan_id == scan_id)

    # Total count
    total_q = select(func.count(Finding.id))
    if scan_id is not None:
        total_q = total_q.where(Finding.scan_id == scan_id)
    total_result = await db.execute(total_q)
    total = total_result.scalar() or 0

    # By severity
    sev_q = (
        select(Finding.severity, func.count(Finding.id))
        .group_by(Finding.severity)
    )
    if scan_id is not None:
        sev_q = sev_q.where(Finding.scan_id == scan_id)
    sev_result = await db.execute(sev_q)
    severity_map = {row[0] or "unknown": row[1] for row in sev_result.all()}

    # By status
    status_q = (
        select(Finding.status, func.count(Finding.id))
        .group_by(Finding.status)
    )
    if scan_id is not None:
        status_q = status_q.where(Finding.scan_id == scan_id)
    status_result = await db.execute(status_q)
    status_map = {row[0]: row[1] for row in status_result.all()}

    # By tool
    tool_q = (
        select(Finding.tool_name, func.count(Finding.id))
        .group_by(Finding.tool_name)
    )
    if scan_id is not None:
        tool_q = tool_q.where(Finding.scan_id == scan_id)
    tool_result = await db.execute(tool_q)
    tool_map = {row[0] or "unknown": row[1] for row in tool_result.all()}

    return FindingSummaryOut(
        total=total,
        critical=severity_map.get("critical", 0),
        high=severity_map.get("high", 0),
        medium=severity_map.get("medium", 0),
        low=severity_map.get("low", 0),
        info=severity_map.get("info", 0),
        by_status=status_map,
        by_tool=tool_map,
    )


@router.get("/by-scan/{scan_id}", response_model=List[FindingOut])
async def get_findings_by_scan(scan_id: int, db: AsyncSession = Depends(get_db)):
    """Get all findings for a specific scan."""
    result = await db.execute(
        select(Finding)
        .where(Finding.scan_id == scan_id)
        .order_by(Finding.severity, Finding.created_at.desc())
    )
    return result.scalars().all()


@router.get("/", response_model=List[FindingOut])
async def list_findings(
    scan_id: Optional[int] = None,
    severity: Optional[str] = None,
    type: Optional[str] = None,
    tool_name: Optional[str] = None,
    finding_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List findings with optional filters."""
    stmt = select(Finding).order_by(Finding.created_at.desc())

    if scan_id is not None:
        stmt = stmt.where(Finding.scan_id == scan_id)
    if severity is not None:
        stmt = stmt.where(Finding.severity == severity)
    if type is not None:
        stmt = stmt.where(Finding.type == type)
    if tool_name is not None:
        stmt = stmt.where(Finding.tool_name == tool_name)
    if finding_status is not None:
        stmt = stmt.where(Finding.status == finding_status)

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{finding_id}", response_model=FindingOut)
async def get_finding(finding_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single finding by ID."""
    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalars().first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


@router.patch("/{finding_id}/status", response_model=FindingOut)
async def update_finding_status(
    finding_id: int,
    payload: FindingStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update the status of a finding."""
    valid_statuses = {"open", "in_progress", "fixed", "false_positive"}
    if payload.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalars().first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    finding.status = payload.status
    await db.commit()
    await db.refresh(finding)
    return finding

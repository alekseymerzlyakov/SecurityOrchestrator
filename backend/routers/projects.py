"""Projects router — CRUD and git operations for projects."""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.project import Project
from backend.models.scan import Scan

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    repo_path: str
    repo_url: Optional[str] = None


class ProjectOut(BaseModel):
    id: int
    name: str
    repo_path: str
    repo_url: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BranchOut(BaseModel):
    branches: List[str]
    current: Optional[str] = None


class AuthorOut(BaseModel):
    authors: List[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """Create a new project."""
    project = Project(
        name=payload.name,
        repo_path=payload.repo_path,
        repo_url=payload.repo_url,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/", response_model=List[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all projects."""
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return result.scalars().all()


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single project by ID."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/branches", response_model=BranchOut)
async def list_project_branches(project_id: int, db: AsyncSession = Depends(get_db)):
    """List git branches for a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        from backend.services.git_manager import list_branches
        branches_info = await list_branches(project.repo_path)
        return BranchOut(
            branches=branches_info.get("branches", []),
            current=branches_info.get("current"),
        )
    except Exception as exc:
        logger.error("Failed to list branches for project %s: %s", project_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to list branches: {exc}")


@router.get("/{project_id}/authors", response_model=AuthorOut)
async def list_project_authors(project_id: int, db: AsyncSession = Depends(get_db)):
    """List commit authors for a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        from backend.services.git_manager import get_commit_authors
        authors = await get_commit_authors(project.repo_path)
        return AuthorOut(authors=authors)
    except Exception as exc:
        logger.error("Failed to list authors for project %s: %s", project_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to list authors: {exc}")


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a project and its associated scans."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete associated scans first (cascade not enforced at ORM level)
    await db.execute(delete(Scan).where(Scan.project_id == project_id))
    await db.delete(project)
    await db.commit()
    return None

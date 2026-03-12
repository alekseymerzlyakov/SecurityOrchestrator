"""Prompts router — manage AI analysis prompt templates."""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.prompt import Prompt

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PromptCreate(BaseModel):
    name: str
    category: Optional[str] = None  # architecture, xss, auth, dependencies, general
    content: str
    is_default: bool = False


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
    is_default: Optional[bool] = None


class PromptOut(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    content: str
    version: int = 1
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/", response_model=PromptOut, status_code=status.HTTP_201_CREATED)
async def create_prompt(payload: PromptCreate, db: AsyncSession = Depends(get_db)):
    """Create a new prompt template."""
    # If this prompt is set as default, unset other defaults in same category
    if payload.is_default and payload.category:
        await db.execute(
            update(Prompt)
            .where(Prompt.category == payload.category, Prompt.is_default == True)
            .values(is_default=False)
        )

    prompt = Prompt(
        name=payload.name,
        category=payload.category,
        content=payload.content,
        is_default=payload.is_default,
        version=1,
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.get("/", response_model=List[PromptOut])
async def list_prompts(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List prompts, optionally filtered by category."""
    stmt = select(Prompt).order_by(Prompt.category, Prompt.name)
    if category is not None:
        stmt = stmt.where(Prompt.category == category)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{prompt_id}", response_model=PromptOut)
async def get_prompt(prompt_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single prompt by ID."""
    result = await db.execute(select(Prompt).where(Prompt.id == prompt_id))
    prompt = result.scalars().first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.put("/{prompt_id}", response_model=PromptOut)
async def update_prompt(
    prompt_id: int,
    payload: PromptUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a prompt and increment its version."""
    result = await db.execute(select(Prompt).where(Prompt.id == prompt_id))
    prompt = result.scalars().first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    if payload.name is not None:
        prompt.name = payload.name
    if payload.category is not None:
        prompt.category = payload.category
    if payload.content is not None:
        prompt.content = payload.content
        # Increment version when content changes
        prompt.version = (prompt.version or 1) + 1
    if payload.is_default is not None:
        prompt.is_default = payload.is_default

    prompt.updated_at = datetime.utcnow()

    # If setting as default, unset others in same category
    if payload.is_default and prompt.category:
        await db.execute(
            update(Prompt)
            .where(
                Prompt.category == prompt.category,
                Prompt.is_default == True,
                Prompt.id != prompt_id,
            )
            .values(is_default=False)
        )

    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(prompt_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a prompt."""
    result = await db.execute(select(Prompt).where(Prompt.id == prompt_id))
    prompt = result.scalars().first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    await db.delete(prompt)
    await db.commit()
    return None


@router.post("/{prompt_id}/set-default", response_model=PromptOut)
async def set_prompt_as_default(prompt_id: int, db: AsyncSession = Depends(get_db)):
    """Set a prompt as the default for its category."""
    result = await db.execute(select(Prompt).where(Prompt.id == prompt_id))
    prompt = result.scalars().first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    if not prompt.category:
        raise HTTPException(
            status_code=400,
            detail="Cannot set as default: prompt has no category",
        )

    # Unset other defaults in this category
    await db.execute(
        update(Prompt)
        .where(
            Prompt.category == prompt.category,
            Prompt.is_default == True,
            Prompt.id != prompt_id,
        )
        .values(is_default=False)
    )

    # Set this one as default
    prompt.is_default = True
    prompt.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(prompt)
    return prompt

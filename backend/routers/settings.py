"""Settings router — AI providers, AI models, and tool configurations."""

import logging
import shutil
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.config import encrypt_value, decrypt_value
from backend.models.settings import AIProvider, AIModel, ToolConfig

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas — Providers
# ---------------------------------------------------------------------------

class ProviderCreate(BaseModel):
    name: str
    provider_type: str  # anthropic / openai / google / ollama
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: bool = True


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None


class ProviderOut(BaseModel):
    id: int
    name: str
    provider_type: str
    api_key_masked: Optional[str] = None
    base_url: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Pydantic schemas — Models
# ---------------------------------------------------------------------------

class ModelCreate(BaseModel):
    provider_id: int
    name: str
    model_id: str
    max_tokens_per_run: int = 1_000_000
    max_budget_usd: float = 50.0
    context_window: Optional[int] = None
    input_price_per_mtok: Optional[float] = None
    output_price_per_mtok: Optional[float] = None
    requests_per_minute: Optional[int] = None
    is_active: bool = True


class ModelUpdate(BaseModel):
    provider_id: Optional[int] = None
    name: Optional[str] = None
    model_id: Optional[str] = None
    max_tokens_per_run: Optional[int] = None
    max_budget_usd: Optional[float] = None
    context_window: Optional[int] = None
    input_price_per_mtok: Optional[float] = None
    output_price_per_mtok: Optional[float] = None
    requests_per_minute: Optional[int] = None
    is_active: Optional[bool] = None


class ModelOut(BaseModel):
    id: int
    provider_id: int
    name: str
    model_id: str
    max_tokens_per_run: int = 1_000_000
    max_budget_usd: float = 50.0
    context_window: Optional[int] = None
    input_price_per_mtok: Optional[float] = None
    output_price_per_mtok: Optional[float] = None
    requests_per_minute: Optional[int] = None
    is_active: bool = True

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Pydantic schemas — Tools
# ---------------------------------------------------------------------------

class ToolUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    config_json: Optional[str] = None
    install_command: Optional[str] = None
    version: Optional[str] = None


class ToolOut(BaseModel):
    id: int
    tool_name: str
    is_enabled: bool = True
    config_json: Optional[str] = None
    install_command: Optional[str] = None
    version: Optional[str] = None

    model_config = {"from_attributes": True}


class ToolCheckOut(BaseModel):
    tool_name: str
    installed: bool
    path: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: mask API key
# ---------------------------------------------------------------------------

def _mask_api_key(encrypted_key: Optional[str]) -> Optional[str]:
    """Return last 4 characters of the decrypted key, masked."""
    if not encrypted_key:
        return None
    try:
        decrypted = decrypt_value(encrypted_key)
        if len(decrypted) <= 4:
            return "****"
        return "*" * (len(decrypted) - 4) + decrypted[-4:]
    except Exception:
        return "****"


def _provider_to_out(provider: AIProvider) -> ProviderOut:
    """Convert a provider ORM object to the output schema."""
    return ProviderOut(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type,
        api_key_masked=_mask_api_key(provider.api_key),
        base_url=provider.base_url,
        is_active=provider.is_active,
        created_at=str(provider.created_at) if provider.created_at else None,
    )


# ===========================================================================
# Provider routes
# ===========================================================================

@router.post("/providers", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(payload: ProviderCreate, db: AsyncSession = Depends(get_db)):
    """Create a new AI provider."""
    provider = AIProvider(
        name=payload.name,
        provider_type=payload.provider_type,
        api_key=encrypt_value(payload.api_key) if payload.api_key else None,
        base_url=payload.base_url,
        is_active=payload.is_active,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return _provider_to_out(provider)


@router.get("/providers", response_model=List[ProviderOut])
async def list_providers(db: AsyncSession = Depends(get_db)):
    """List all AI providers."""
    result = await db.execute(select(AIProvider).order_by(AIProvider.id))
    providers = result.scalars().all()
    return [_provider_to_out(p) for p in providers]


@router.get("/providers/{provider_id}", response_model=ProviderOut)
async def get_provider(provider_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single AI provider."""
    result = await db.execute(select(AIProvider).where(AIProvider.id == provider_id))
    provider = result.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _provider_to_out(provider)


@router.put("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: int,
    payload: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an AI provider."""
    result = await db.execute(select(AIProvider).where(AIProvider.id == provider_id))
    provider = result.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if payload.name is not None:
        provider.name = payload.name
    if payload.provider_type is not None:
        provider.provider_type = payload.provider_type
    if payload.api_key is not None:
        provider.api_key = encrypt_value(payload.api_key)
    if payload.base_url is not None:
        provider.base_url = payload.base_url
    if payload.is_active is not None:
        provider.is_active = payload.is_active

    await db.commit()
    await db.refresh(provider)
    return _provider_to_out(provider)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(provider_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an AI provider and its associated models."""
    result = await db.execute(select(AIProvider).where(AIProvider.id == provider_id))
    provider = result.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Delete associated models first
    await db.execute(delete(AIModel).where(AIModel.provider_id == provider_id))
    await db.delete(provider)
    await db.commit()
    return None


# ===========================================================================
# Model routes
# ===========================================================================

@router.post("/models", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
async def create_model(payload: ModelCreate, db: AsyncSession = Depends(get_db)):
    """Create a new AI model."""
    # Verify provider exists
    result = await db.execute(select(AIProvider).where(AIProvider.id == payload.provider_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Provider not found")

    model = AIModel(
        provider_id=payload.provider_id,
        name=payload.name,
        model_id=payload.model_id,
        max_tokens_per_run=payload.max_tokens_per_run,
        max_budget_usd=payload.max_budget_usd,
        context_window=payload.context_window,
        input_price_per_mtok=payload.input_price_per_mtok,
        output_price_per_mtok=payload.output_price_per_mtok,
        requests_per_minute=payload.requests_per_minute,
        is_active=payload.is_active,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


@router.get("/models", response_model=List[ModelOut])
async def list_models(
    provider_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List AI models, optionally filtered by provider."""
    stmt = select(AIModel).order_by(AIModel.id)
    if provider_id is not None:
        stmt = stmt.where(AIModel.provider_id == provider_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/models/{model_id}", response_model=ModelOut)
async def get_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single AI model."""
    result = await db.execute(select(AIModel).where(AIModel.id == model_id))
    model = result.scalars().first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.put("/models/{model_id}", response_model=ModelOut)
async def update_model(
    model_id: int,
    payload: ModelUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an AI model."""
    result = await db.execute(select(AIModel).where(AIModel.id == model_id))
    model = result.scalars().first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(model, field, value)

    await db.commit()
    await db.refresh(model)
    return model


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an AI model."""
    result = await db.execute(select(AIModel).where(AIModel.id == model_id))
    model = result.scalars().first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    await db.delete(model)
    await db.commit()
    return None


# ===========================================================================
# Tool config routes
# ===========================================================================

@router.get("/tools", response_model=List[ToolOut])
async def list_tools(db: AsyncSession = Depends(get_db)):
    """List all tool configurations."""
    result = await db.execute(select(ToolConfig).order_by(ToolConfig.id))
    return result.scalars().all()


@router.get("/tools/{tool_id}", response_model=ToolOut)
async def get_tool(tool_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single tool configuration."""
    result = await db.execute(select(ToolConfig).where(ToolConfig.id == tool_id))
    tool = result.scalars().first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.put("/tools/{tool_id}", response_model=ToolOut)
async def update_tool(
    tool_id: int,
    payload: ToolUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a tool configuration (enable/disable, change config)."""
    result = await db.execute(select(ToolConfig).where(ToolConfig.id == tool_id))
    tool = result.scalars().first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tool, field, value)

    await db.commit()
    await db.refresh(tool)
    return tool


@router.get("/tools/{tool_name}/check", response_model=ToolCheckOut)
async def check_tool_installed(tool_name: str):
    """Check if a security tool is installed on the system."""
    # Map internal tool names to CLI binary names
    binary_map = {
        "semgrep": "semgrep",
        "gitleaks": "gitleaks",
        "trivy": "trivy",
        "npm_audit": "npm",
        "eslint_security": "eslint",
        "retirejs": "retire",
    }
    binary = binary_map.get(tool_name, tool_name)
    path = shutil.which(binary)
    return ToolCheckOut(
        tool_name=tool_name,
        installed=path is not None,
        path=path,
    )

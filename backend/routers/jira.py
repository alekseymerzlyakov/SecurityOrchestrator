"""Jira router — configuration, connection testing, and ticket creation."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.config import encrypt_value, decrypt_value
from backend.models.settings import JiraConfig
from backend.models.scan import Finding

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class JiraConfigCreate(BaseModel):
    base_url: str
    api_token: Optional[str] = None
    user_email: Optional[str] = None
    project_key: str
    issue_type: str = "Bug"
    priority_mapping: Optional[str] = None  # JSON string
    is_active: bool = True


class JiraConfigUpdate(BaseModel):
    base_url: Optional[str] = None
    api_token: Optional[str] = None
    user_email: Optional[str] = None
    project_key: Optional[str] = None
    issue_type: Optional[str] = None
    priority_mapping: Optional[str] = None
    is_active: Optional[bool] = None


class JiraConfigOut(BaseModel):
    id: int
    base_url: str
    api_token_masked: Optional[str] = None
    user_email: Optional[str] = None
    project_key: str
    issue_type: str = "Bug"
    priority_mapping: Optional[str] = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class JiraTestResult(BaseModel):
    success: bool
    message: str


class JiraTicketResult(BaseModel):
    success: bool
    ticket_id: Optional[str] = None
    ticket_url: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_token(encrypted_token: Optional[str]) -> Optional[str]:
    """Return last 4 characters of the decrypted token, masked."""
    if not encrypted_token:
        return None
    try:
        decrypted = decrypt_value(encrypted_token)
        if len(decrypted) <= 4:
            return "****"
        return "*" * (len(decrypted) - 4) + decrypted[-4:]
    except Exception:
        return "****"


def _config_to_out(config: JiraConfig) -> JiraConfigOut:
    """Convert a JiraConfig ORM object to the output schema."""
    return JiraConfigOut(
        id=config.id,
        base_url=config.base_url,
        api_token_masked=_mask_token(config.api_token),
        user_email=config.user_email,
        project_key=config.project_key,
        issue_type=config.issue_type,
        priority_mapping=config.priority_mapping,
        is_active=config.is_active,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/config", response_model=Optional[JiraConfigOut])
async def get_jira_config(db: AsyncSession = Depends(get_db)):
    """Get the current Jira configuration (token masked)."""
    result = await db.execute(select(JiraConfig).order_by(JiraConfig.id.desc()).limit(1))
    config = result.scalars().first()
    if not config:
        return None
    return _config_to_out(config)


@router.post("/config", response_model=JiraConfigOut, status_code=status.HTTP_201_CREATED)
async def create_jira_config(
    payload: JiraConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """Save a new Jira configuration."""
    config = JiraConfig(
        base_url=payload.base_url,
        api_token=encrypt_value(payload.api_token) if payload.api_token else None,
        user_email=payload.user_email,
        project_key=payload.project_key,
        issue_type=payload.issue_type,
        priority_mapping=payload.priority_mapping,
        is_active=payload.is_active,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return _config_to_out(config)


@router.put("/config/{config_id}", response_model=JiraConfigOut)
async def update_jira_config(
    config_id: int,
    payload: JiraConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing Jira configuration."""
    result = await db.execute(select(JiraConfig).where(JiraConfig.id == config_id))
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail="Jira configuration not found")

    if payload.base_url is not None:
        config.base_url = payload.base_url
    if payload.api_token is not None:
        config.api_token = encrypt_value(payload.api_token)
    if payload.user_email is not None:
        config.user_email = payload.user_email
    if payload.project_key is not None:
        config.project_key = payload.project_key
    if payload.issue_type is not None:
        config.issue_type = payload.issue_type
    if payload.priority_mapping is not None:
        config.priority_mapping = payload.priority_mapping
    if payload.is_active is not None:
        config.is_active = payload.is_active

    await db.commit()
    await db.refresh(config)
    return _config_to_out(config)


@router.post("/test-connection", response_model=JiraTestResult)
async def test_jira_connection(db: AsyncSession = Depends(get_db)):
    """Test the Jira connection using the stored configuration."""
    result = await db.execute(select(JiraConfig).where(JiraConfig.is_active == True).limit(1))
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail="No active Jira configuration found")

    try:
        from backend.services.jira_service import test_jira_connection

        # Decrypt the token for the service call
        decrypted_token = decrypt_value(config.api_token) if config.api_token else None
        success, message = await test_jira_connection(
            base_url=config.base_url,
            api_token=decrypted_token,
            user_email=config.user_email,
        )
        return JiraTestResult(success=success, message=message)
    except ImportError:
        return JiraTestResult(
            success=False,
            message="Jira service not yet implemented. Connection test will be available in a future phase.",
        )
    except Exception as exc:
        logger.error("Jira connection test failed: %s", exc)
        return JiraTestResult(success=False, message=f"Connection failed: {exc}")


@router.post("/create-ticket/{finding_id}", response_model=JiraTicketResult)
async def create_jira_ticket(finding_id: int, db: AsyncSession = Depends(get_db)):
    """Create a Jira ticket from a security finding."""
    # Validate finding
    finding_result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = finding_result.scalars().first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    # Check if ticket already exists
    if finding.jira_ticket_id:
        return JiraTicketResult(
            success=True,
            ticket_id=finding.jira_ticket_id,
            ticket_url=finding.jira_ticket_url,
            message="Jira ticket already exists for this finding",
        )

    # Get active Jira config
    config_result = await db.execute(
        select(JiraConfig).where(JiraConfig.is_active == True).limit(1)
    )
    config = config_result.scalars().first()
    if not config:
        raise HTTPException(status_code=404, detail="No active Jira configuration found")

    try:
        from backend.services.jira_service import create_jira_ticket as create_ticket

        decrypted_token = decrypt_value(config.api_token) if config.api_token else None

        ticket_result = await create_ticket(
            base_url=config.base_url,
            api_token=decrypted_token,
            user_email=config.user_email,
            project_key=config.project_key,
            issue_type=config.issue_type,
            priority_mapping=config.priority_mapping,
            finding={
                "id": finding.id,
                "title": finding.title,
                "description": finding.description,
                "severity": finding.severity,
                "type": finding.type,
                "file_path": finding.file_path,
                "line_start": finding.line_start,
                "line_end": finding.line_end,
                "code_snippet": finding.code_snippet,
                "tool_name": finding.tool_name,
                "cwe_id": finding.cwe_id,
                "cvss_score": finding.cvss_score,
                "recommendation": finding.recommendation,
            },
        )

        # Update finding with ticket info
        if ticket_result.get("success"):
            finding.jira_ticket_id = ticket_result["ticket_id"]
            finding.jira_ticket_url = ticket_result["ticket_url"]
            finding.status = "in_progress"
            await db.commit()

        return JiraTicketResult(
            success=ticket_result.get("success", False),
            ticket_id=ticket_result.get("ticket_id"),
            ticket_url=ticket_result.get("ticket_url"),
            message=ticket_result.get("message", "Ticket created"),
        )
    except ImportError:
        return JiraTicketResult(
            success=False,
            message="Jira service not yet implemented. Ticket creation will be available in a future phase.",
        )
    except Exception as exc:
        logger.error("Failed to create Jira ticket for finding %s: %s", finding_id, exc)
        return JiraTicketResult(success=False, message=f"Failed to create ticket: {exc}")

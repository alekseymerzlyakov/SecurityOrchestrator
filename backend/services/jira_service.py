"""Jira REST API v2 integration service.

Provides functions to test Jira connectivity and create tickets
from security findings.
"""

import json
import logging
from typing import Any

import httpx

from backend.models.scan import Finding
from backend.models.settings import JiraConfig

logger = logging.getLogger(__name__)

# Default timeout for Jira API calls (seconds)
DEFAULT_TIMEOUT = 30.0


def _build_auth(email: str, api_token: str) -> httpx.BasicAuth:
    """Build HTTP basic auth for Jira Cloud (email:api_token)."""
    return httpx.BasicAuth(username=email, password=api_token)


def _api_url(base_url: str, path: str) -> str:
    """Build full Jira API URL."""
    base = base_url.rstrip("/")
    return f"{base}{path}"


# ---------------------------------------------------------------------------
# Test connection
# ---------------------------------------------------------------------------

async def test_connection(base_url: str, email: str, api_token: str) -> bool:
    """Test Jira connectivity by calling GET /rest/api/2/myself.

    Returns True if the response is 200 and contains accountId or name.
    """
    url = _api_url(base_url, "/rest/api/2/myself")
    auth = _build_auth(email, api_token)

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, auth=auth)

        if resp.status_code == 200:
            data = resp.json()
            user = data.get("displayName") or data.get("name") or data.get("accountId")
            logger.info("Jira connection successful. Authenticated as: %s", user)
            return True
        else:
            logger.warning(
                "Jira connection failed: HTTP %d — %s",
                resp.status_code,
                resp.text[:200],
            )
            return False

    except httpx.HTTPError as exc:
        logger.error("Jira connection error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Create ticket
# ---------------------------------------------------------------------------

async def create_ticket(finding: Finding, jira_config: JiraConfig) -> dict[str, str]:
    """Create a Jira issue from a security finding.

    Args:
        finding: The Finding ORM object to create a ticket for.
        jira_config: JiraConfig ORM object with connection details.

    Returns:
        Dict with 'ticket_id' and 'ticket_url', or empty dict on failure.
    """
    url = _api_url(jira_config.base_url, "/rest/api/2/issue")
    auth = _build_auth(jira_config.user_email, jira_config.api_token)

    # Parse priority mapping
    try:
        priority_mapping = json.loads(jira_config.priority_mapping)
    except (json.JSONDecodeError, TypeError):
        priority_mapping = {
            "critical": "Highest",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
            "info": "Lowest",
        }

    # Map finding severity to Jira priority
    jira_priority = priority_mapping.get(
        finding.severity or "medium",
        "Medium",
    )

    # Build the description in Jira wiki markup
    description = _format_description(finding)

    # Build the issue payload
    payload: dict[str, Any] = {
        "fields": {
            "project": {
                "key": jira_config.project_key,
            },
            "summary": _build_summary(finding),
            "description": description,
            "issuetype": {
                "name": jira_config.issue_type or "Bug",
            },
            "priority": {
                "name": jira_priority,
            },
            "labels": _build_labels(finding),
        }
    }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                url,
                json=payload,
                auth=auth,
                headers={"Content-Type": "application/json"},
            )

        if resp.status_code in (200, 201):
            data = resp.json()
            ticket_key = data.get("key", "")
            ticket_id = data.get("id", "")
            ticket_url = f"{jira_config.base_url.rstrip('/')}/browse/{ticket_key}"

            logger.info("Jira ticket created: %s (%s)", ticket_key, ticket_url)
            return {
                "ticket_id": ticket_key,
                "ticket_url": ticket_url,
            }
        else:
            logger.error(
                "Failed to create Jira ticket: HTTP %d — %s",
                resp.status_code,
                resp.text[:500],
            )
            return {}

    except httpx.HTTPError as exc:
        logger.error("Jira API error creating ticket: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _build_summary(finding: Finding) -> str:
    """Build a concise Jira issue summary from a finding."""
    severity_prefix = f"[{(finding.severity or 'medium').upper()}]"
    title = finding.title or "Security Finding"
    # Jira summary has a 255 char limit
    summary = f"{severity_prefix} {title}"
    return summary[:255]


def _build_labels(finding: Finding) -> list[str]:
    """Build Jira labels from finding metadata."""
    labels = ["security", "aiso"]
    if finding.severity:
        labels.append(f"severity-{finding.severity}")
    if finding.type:
        labels.append(f"type-{finding.type}")
    if finding.tool_name:
        labels.append(f"tool-{finding.tool_name}")
    return labels


def _format_description(finding: Finding) -> str:
    """Format the finding into Jira wiki markup for the description field."""
    lines: list[str] = []

    lines.append("h2. Security Finding")
    lines.append("")

    # Severity and confidence
    lines.append(f"||Severity|{(finding.severity or 'medium').upper()}||")
    if finding.confidence:
        lines.append(f"||Confidence|{finding.confidence.upper()}||")
    if finding.type:
        lines.append(f"||Type|{finding.type}||")
    if finding.tool_name:
        lines.append(f"||Detected by|{finding.tool_name}||")
    if finding.cwe_id:
        lines.append(f"||CWE|[{finding.cwe_id}|https://cwe.mitre.org/data/definitions/{finding.cwe_id.replace('CWE-', '')}.html]||")

    lines.append("")

    # Location
    if finding.file_path:
        lines.append("h3. Location")
        location = f"*File:* {{{{monospace|{finding.file_path}}}}}"
        if finding.line_start:
            location += f" (line {finding.line_start}"
            if finding.line_end and finding.line_end != finding.line_start:
                location += f"-{finding.line_end}"
            location += ")"
        lines.append(location)
        lines.append("")

    # Code snippet
    if finding.code_snippet:
        lines.append("h3. Code Snippet")
        lines.append("{code}")
        lines.append(finding.code_snippet)
        lines.append("{code}")
        lines.append("")

    # Description
    if finding.description:
        lines.append("h3. Description")
        lines.append(finding.description)
        lines.append("")

    # Recommendation
    if finding.recommendation:
        lines.append("h3. Recommendation")
        lines.append(finding.recommendation)
        lines.append("")

    # Commit info
    if finding.commit_author or finding.commit_date:
        lines.append("h3. Commit Information")
        if finding.commit_author:
            lines.append(f"*Author:* {finding.commit_author}")
        if finding.commit_date:
            lines.append(f"*Date:* {finding.commit_date}")
        lines.append("")

    lines.append("----")
    lines.append("_Generated by AISO (AI-Driven Security Orchestrator)_")

    return "\n".join(lines)

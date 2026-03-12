"""Token accounting and cost estimation for AI-powered security scans.

Tracks token usage per scan, estimates costs before running, and enforces
budget limits to prevent runaway spending.
"""

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models.scan import Scan, TokenUsage
from backend.models.settings import AIModel, AIProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Approximate token count for a text string.

    Uses tiktoken (cl100k_base) if available, otherwise falls back to a
    character-based heuristic (~4 chars per token).

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except (ImportError, Exception):
        # Fallback: ~4 characters per token
        return max(1, len(text) // 4)


def _calculate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_mtok: float,
    output_price_per_mtok: float,
) -> float:
    """Calculate cost in USD given token counts and pricing.

    Args:
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.
        input_price_per_mtok: Price per million input tokens.
        output_price_per_mtok: Price per million output tokens.

    Returns:
        Total cost in USD.
    """
    input_cost = (input_tokens / 1_000_000) * input_price_per_mtok
    output_cost = (output_tokens / 1_000_000) * output_price_per_mtok
    return input_cost + output_cost


# ---------------------------------------------------------------------------
# Pre-scan cost estimation
# ---------------------------------------------------------------------------

async def estimate_scan_cost(
    repo_path: str,
    model: dict,
    max_tokens_per_chunk: int = 120_000,
) -> dict:
    """Predict tokens and cost for a full repository scan.

    Args:
        repo_path: Path to the repository.
        model: Dict with model info including pricing:
            {model_id, input_price_per_mtok, output_price_per_mtok,
             context_window, max_tokens_per_run, max_budget_usd}
        max_tokens_per_chunk: Token budget per chunk.

    Returns:
        {
            "total_code_tokens": int,
            "estimated_chunks": int,
            "estimated_input_tokens": int,
            "estimated_output_tokens": int,
            "estimated_input_cost": float,
            "estimated_output_cost": float,
            "estimated_total_cost": float,
            "total_files": int,
        }
    """
    repo = Path(repo_path)
    if not repo.is_dir():
        raise FileNotFoundError(f"Repository not found: {repo_path}")

    # Count total code tokens across the project
    total_code_tokens = 0
    total_files = 0

    # Re-use the chunking module's file discovery logic
    from backend.services.chunking import build_project_map

    project_map = await build_project_map(repo_path)
    total_files = project_map["total_files"]

    for f in project_map["files"]:
        total_code_tokens += f["estimated_tokens"]

    # Estimate number of chunks
    estimated_chunks = max(1, (total_code_tokens + max_tokens_per_chunk - 1) // max_tokens_per_chunk)

    # Each chunk's input = system prompt (~2000 tokens) + chunk context
    system_prompt_tokens = 2000
    avg_chunk_input = min(max_tokens_per_chunk, total_code_tokens // estimated_chunks) if estimated_chunks > 0 else 0
    estimated_input_per_chunk = system_prompt_tokens + avg_chunk_input

    # Estimate output: assume ~20% of input as output (findings JSON)
    estimated_output_per_chunk = min(8192, int(avg_chunk_input * 0.2))

    total_input = estimated_input_per_chunk * estimated_chunks
    total_output = estimated_output_per_chunk * estimated_chunks

    input_price = model.get("input_price_per_mtok", 0.0)
    output_price = model.get("output_price_per_mtok", 0.0)

    input_cost = (total_input / 1_000_000) * input_price
    output_cost = (total_output / 1_000_000) * output_price

    return {
        "total_code_tokens": total_code_tokens,
        "estimated_chunks": estimated_chunks,
        "estimated_input_tokens": total_input,
        "estimated_output_tokens": total_output,
        "estimated_input_cost": round(input_cost, 6),
        "estimated_output_cost": round(output_cost, 6),
        "estimated_total_cost": round(input_cost + output_cost, 6),
        "total_files": total_files,
    }


# ---------------------------------------------------------------------------
# Usage logging
# ---------------------------------------------------------------------------

async def log_usage(
    scan_id: int,
    model_id: int,
    input_tokens: int,
    output_tokens: int,
    chunk_desc: str,
    input_price_per_mtok: float = 0.0,
    output_price_per_mtok: float = 0.0,
) -> None:
    """Save token usage record to the database.

    Args:
        scan_id: The scan this usage belongs to.
        model_id: The AI model ID used.
        input_tokens: Input tokens consumed.
        output_tokens: Output tokens consumed.
        chunk_desc: Description of the chunk (e.g., "chunk 1/5 - src/auth/").
        input_price_per_mtok: Input pricing for cost calculation.
        output_price_per_mtok: Output pricing for cost calculation.
    """
    cost = _calculate_cost(input_tokens, output_tokens, input_price_per_mtok, output_price_per_mtok)

    async with async_session() as session:
        usage = TokenUsage(
            scan_id=scan_id,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            chunk_description=chunk_desc,
            timestamp=datetime.utcnow(),
        )
        session.add(usage)

        # Also update the running totals on the Scan record
        result = await session.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalars().first()
        if scan:
            scan.tokens_used = (scan.tokens_used or 0) + input_tokens + output_tokens
            scan.cost_usd = round((scan.cost_usd or 0.0) + cost, 6)

        await session.commit()

    logger.info(
        "Token usage logged: scan=%d, chunk=%s, in=%d, out=%d, cost=$%.6f",
        scan_id, chunk_desc, input_tokens, output_tokens, cost,
    )


# ---------------------------------------------------------------------------
# Budget checking
# ---------------------------------------------------------------------------

async def check_budget(scan_id: int, model: dict) -> dict:
    """Check remaining budget for a scan.

    Args:
        scan_id: The scan to check.
        model: Dict with model limits:
            {max_tokens_per_run, max_budget_usd}

    Returns:
        {
            "tokens_used": int,
            "cost_used": float,
            "tokens_remaining": int,
            "budget_remaining": float,
            "should_stop": bool,
            "percent_complete_tokens": float,
            "percent_complete_budget": float,
        }
    """
    max_tokens = model.get("max_tokens_per_run", 1_000_000)
    max_budget = model.get("max_budget_usd", 50.0)

    async with async_session() as session:
        # Sum up all token usage for this scan
        result = await session.execute(
            select(
                func.coalesce(func.sum(TokenUsage.input_tokens + TokenUsage.output_tokens), 0),
                func.coalesce(func.sum(TokenUsage.cost_usd), 0.0),
            ).where(TokenUsage.scan_id == scan_id)
        )
        row = result.one()
        tokens_used = int(row[0])
        cost_used = float(row[1])

    tokens_remaining = max(0, max_tokens - tokens_used)
    budget_remaining = max(0.0, max_budget - cost_used)

    pct_tokens = round((tokens_used / max_tokens * 100), 2) if max_tokens > 0 else 0.0
    pct_budget = round((cost_used / max_budget * 100), 2) if max_budget > 0 else 0.0

    # Stop if either limit is reached
    should_stop = tokens_remaining <= 0 or budget_remaining <= 0.0

    return {
        "tokens_used": tokens_used,
        "cost_used": round(cost_used, 6),
        "tokens_remaining": tokens_remaining,
        "budget_remaining": round(budget_remaining, 6),
        "should_stop": should_stop,
        "percent_complete_tokens": pct_tokens,
        "percent_complete_budget": pct_budget,
    }


# ---------------------------------------------------------------------------
# Cost summary
# ---------------------------------------------------------------------------

async def get_cost_summary(scan_id: int) -> dict:
    """Get a full cost report for a completed or in-progress scan.

    Args:
        scan_id: The scan to report on.

    Returns:
        {
            "scan_id": int,
            "total_input_tokens": int,
            "total_output_tokens": int,
            "total_tokens": int,
            "total_cost_usd": float,
            "chunks_processed": int,
            "breakdown": [
                {"chunk": str, "input_tokens": int, "output_tokens": int, "cost": float},
                ...
            ]
        }
    """
    async with async_session() as session:
        result = await session.execute(
            select(TokenUsage)
            .where(TokenUsage.scan_id == scan_id)
            .order_by(TokenUsage.timestamp)
        )
        records = result.scalars().all()

    total_input = 0
    total_output = 0
    total_cost = 0.0
    breakdown: list[dict] = []

    for record in records:
        total_input += record.input_tokens
        total_output += record.output_tokens
        total_cost += record.cost_usd
        breakdown.append({
            "chunk": record.chunk_description or "unknown",
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "cost": round(record.cost_usd, 6),
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        })

    return {
        "scan_id": scan_id,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_cost_usd": round(total_cost, 6),
        "chunks_processed": len(records),
        "breakdown": breakdown,
    }

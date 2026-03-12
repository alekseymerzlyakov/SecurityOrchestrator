"""AI analysis engine — orchestrates chunked code analysis via AI providers.

Workflow:
1. Load model config + provider from DB
2. Build project map, prioritize files
3. Create chunks in priority order
4. For each chunk: check budget → build context → call AI → parse findings → save
5. On budget exceeded: stop, generate partial report
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, update

from backend.database import async_session
from backend.models.scan import Scan, Finding, TokenUsage
from backend.models.settings import AIModel, AIProvider
from backend.models.prompt import Prompt
from backend.websocket.manager import ws_manager
from backend.services.tool_runners.base import ToolFinding
from backend.services.chunking import build_project_map, prioritize_files, create_chunks, build_chunk_context
from backend.services.token_tracker import estimate_tokens, log_usage, check_budget, estimate_scan_cost
from backend.services.ai_providers.base import BaseAIProvider, AIResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDER_CLASSES: dict[str, type[BaseAIProvider]] = {}


def _load_provider_classes():
    """Lazy-load provider implementations. Each provider is imported
    individually so a missing optional dependency (e.g. google-generativeai)
    doesn't break the others."""
    global _PROVIDER_CLASSES
    if _PROVIDER_CLASSES:
        return

    candidates = {
        "anthropic": "backend.services.ai_providers.anthropic_provider.AnthropicProvider",
        "openai":    "backend.services.ai_providers.openai_provider.OpenAIProvider",
        "google":    "backend.services.ai_providers.google_provider.GoogleProvider",
        "ollama":    "backend.services.ai_providers.ollama_provider.OllamaProvider",
    }

    for provider_type, dotted_path in candidates.items():
        try:
            module_path, class_name = dotted_path.rsplit(".", 1)
            import importlib
            mod = importlib.import_module(module_path)
            _PROVIDER_CLASSES[provider_type] = getattr(mod, class_name)
        except Exception as exc:
            logger.debug("Provider '%s' not available: %s", provider_type, exc)


def get_provider(provider_type: str) -> BaseAIProvider:
    """Get an AI provider instance by type."""
    _load_provider_classes()
    cls = _PROVIDER_CLASSES.get(provider_type)
    if cls is None:
        raise ValueError(f"Unknown AI provider type: {provider_type}")
    return cls()


# ---------------------------------------------------------------------------
# Security prompts — mode-aware loading
# ---------------------------------------------------------------------------

# File-based prompt cache: filename -> content
_PROMPT_CACHE: dict[str, str] = {}

_FALLBACK_PROMPT = (
    "You are a security auditor. Analyze the following code for vulnerabilities. "
    "Return findings as a JSON array with title, severity, type, cwe_id, cvss_score, "
    "file_path, line_start, line_end, code_snippet, description, recommendation, confidence."
)


def _load_prompt_file(filename: str) -> str:
    """Load a prompt from the prompts directory, with caching."""
    if filename in _PROMPT_CACHE:
        return _PROMPT_CACHE[filename]
    from backend.config import PROMPTS_DIR
    prompt_file = PROMPTS_DIR / filename
    if prompt_file.exists():
        content = prompt_file.read_text(encoding="utf-8")
        _PROMPT_CACHE[filename] = content
        return content
    return ""


def _load_prompt_for_mode(mode: str) -> str:
    """Return the appropriate built-in prompt based on scan mode.

    - hybrid   → hybrid_focused.txt  (verify SAST findings, find exploit chains)
    - ai_only  → ai_only_deep_scan.txt  (full independent audit)
    - fallback → inline default prompt
    """
    filename = "hybrid_focused.txt" if mode == "hybrid" else "ai_only_deep_scan.txt"
    content = _load_prompt_file(filename)
    if content:
        logger.debug("Loaded prompt for mode=%s from %s", mode, filename)
        return content
    # Final fallback — older default_security.txt
    legacy = _load_prompt_file("default_security.txt")
    return legacy if legacy else _FALLBACK_PROMPT


# Keep for backward compatibility
def _load_default_prompt() -> str:
    return _load_prompt_for_mode("ai_only")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_ai_findings(response_text: str, tool_name: str = "ai_analysis") -> list[ToolFinding]:
    """Parse AI response text into ToolFinding objects.

    The AI should return a JSON array of finding objects.
    We try multiple strategies to extract the JSON.
    """
    findings = []

    # Try to extract JSON array from response
    json_data = None

    # Strategy 1: direct parse
    try:
        json_data = json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: find JSON array in markdown code block
    if json_data is None:
        match = re.search(r'```(?:json)?\s*\n(\[.*?\])\s*\n```', response_text, re.DOTALL)
        if match:
            try:
                json_data = json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

    # Strategy 3: find any JSON array
    if json_data is None:
        match = re.search(r'\[[\s\S]*\]', response_text)
        if match:
            try:
                json_data = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    if json_data is None:
        logger.warning("Could not parse AI response as JSON array")
        # If the AI says "no vulnerabilities found", return empty
        if any(phrase in response_text.lower() for phrase in [
            "no vulnerabilities", "no security issues", "no findings",
            "appears secure", "empty array", "[]"
        ]):
            return []
        # Otherwise log the raw response for debugging
        logger.debug("Raw AI response: %s", response_text[:500])
        return []

    if not isinstance(json_data, list):
        json_data = [json_data]

    for item in json_data:
        if not isinstance(item, dict):
            continue

        findings.append(ToolFinding(
            title=item.get("title", "AI-detected issue"),
            description=item.get("description", ""),
            severity=item.get("severity", "medium").lower(),
            type=item.get("type", ""),
            file_path=item.get("file_path", ""),
            line_start=item.get("line_start", 0),
            line_end=item.get("line_end", 0),
            code_snippet=item.get("code_snippet", ""),
            confidence=item.get("confidence", "medium").lower(),
            cwe_id=item.get("cwe_id", ""),
            tool_name=tool_name,
            recommendation=item.get("recommendation", ""),
        ))

    return findings


# ---------------------------------------------------------------------------
# Main AI analysis entry point
# ---------------------------------------------------------------------------

async def run_ai_analysis(
    scan_id: int,
    step_id: int,
    repo_path: str,
    branch: str,
    config: dict = None,
) -> tuple[list[ToolFinding], int, float]:
    """Run AI-powered security analysis on a repository.

    Args:
        scan_id: ID of the scan
        step_id: ID of the scan step
        repo_path: Path to the repository
        branch: Git branch being scanned
        config: Optional config with model_id, prompt_id, etc.

    Returns:
        Tuple of (findings, total_tokens_used, total_cost_usd)
    """
    config = config or {}
    model_id = config.get("model_id")
    prompt_id = config.get("prompt_id")

    all_findings: list[ToolFinding] = []
    total_tokens = 0
    total_cost = 0.0

    # 1. Load AI model and provider config from DB
    async with async_session() as session:
        if model_id:
            result = await session.execute(
                select(AIModel).where(AIModel.id == model_id)
            )
            model = result.scalars().first()
        else:
            # Use first active model
            result = await session.execute(
                select(AIModel).where(AIModel.is_active == True).limit(1)
            )
            model = result.scalars().first()

        if not model:
            logger.error("No AI model configured for scan %d", scan_id)
            return [], 0, 0.0

        # Load provider
        result = await session.execute(
            select(AIProvider).where(AIProvider.id == model.provider_id)
        )
        provider_record = result.scalars().first()

        if not provider_record:
            logger.error("AI provider %d not found", model.provider_id)
            return [], 0, 0.0

        # Load prompt: explicit prompt_id overrides mode-based auto-selection
        scan_mode_for_prompt = config.get("mode", "ai_only")
        system_prompt = _load_prompt_for_mode(scan_mode_for_prompt)
        logger.info(
            "Scan %d: using prompt for mode=%s (prompt_id=%s)",
            scan_id, scan_mode_for_prompt, prompt_id,
        )
        if prompt_id:
            result = await session.execute(
                select(Prompt).where(Prompt.id == prompt_id)
            )
            prompt_record = result.scalars().first()
            if prompt_record:
                system_prompt = prompt_record.content
                logger.info(
                    "Scan %d: user-selected prompt '%s' overrides mode default",
                    scan_id, prompt_record.name,
                )

    # 2. Decrypt API key
    from backend.config import decrypt_value
    api_key = None
    if provider_record.api_key:
        try:
            api_key = decrypt_value(provider_record.api_key)
        except Exception:
            logger.error("Failed to decrypt API key for provider %s", provider_record.name)
            return [], 0, 0.0

    # 3. Get provider instance
    try:
        provider = get_provider(provider_record.provider_type)
    except ValueError as e:
        logger.error(str(e))
        return [], 0, 0.0

    # 4. Build project map
    logger.info("Scan %d: building project map for %s", scan_id, repo_path)
    await ws_manager.send_scan_progress(
        scan_id=scan_id,
        step_name="ai_analysis",
        status="running",
        files_processed=0,
        total_files=1,
        message="Building project map...",
    )

    project_map = await build_project_map(repo_path)

    # 5. Gather existing SAST findings for context
    sast_findings = []
    async with async_session() as session:
        from backend.models.scan import Finding as FindingModel
        result = await session.execute(
            select(FindingModel).where(
                FindingModel.scan_id == scan_id,
                FindingModel.tool_name != "ai_analysis",
            )
        )
        for f in result.scalars().all():
            sast_findings.append({
                "file_path": f.file_path,
                "title": f.title,
                "severity": f.severity,
                "tool_name": f.tool_name,
                "line_start": f.line_start,
            })

    # 6. Prioritize files
    tiers = prioritize_files(project_map["files"], sast_findings)

    # Smart Hybrid mode: if we have SAST findings, restrict AI to only files
    # that have findings + their directory neighbors. This mirrors how top tools
    # (Snyk, CodeQL, Semgrep Pro) work — tools map the surface, AI digs deep
    # into flagged hotspots rather than wasting budget on clean files.
    scan_mode = config.get("mode", "ai_only")
    sast_file_paths = {f["file_path"] for f in sast_findings if f.get("file_path")}
    has_sast_data = bool(sast_file_paths)

    if scan_mode == "hybrid" and has_sast_data:
        # Collect flagged files + same-directory neighbors (they often share context)
        flagged_dirs = {str(Path(p).parent) for p in sast_file_paths}
        all_file_paths = {f["path"] for f in project_map["files"]}

        # Neighbors = files in the same directory as any flagged file
        neighbor_paths = {
            p for p in all_file_paths
            if str(Path(p).parent) in flagged_dirs and p not in sast_file_paths
        }

        # Build focused file list: flagged first (tier1 from SAST), then neighbors
        flagged_files = [f for f in project_map["files"] if f["path"] in sast_file_paths]
        neighbor_files = [f for f in project_map["files"] if f["path"] in neighbor_paths]

        # Also add high-priority files from tier1 (auth/crypto/etc) even if no SAST finding
        tier1_extra = [
            f for f in tiers["tier1"]
            if f["path"] not in sast_file_paths and f["path"] not in neighbor_paths
        ]

        ordered_files = flagged_files + tier1_extra + neighbor_files

        logger.info(
            "Scan %d [SMART HYBRID]: %d flagged files, %d tier1 extras, %d neighbors "
            "(skipping %d clean files)",
            scan_id,
            len(flagged_files),
            len(tier1_extra),
            len(neighbor_files),
            len(project_map["files"]) - len(ordered_files),
        )

        await ws_manager.send_scan_progress(
            scan_id=scan_id,
            step_name="ai_analysis",
            status="running",
            files_processed=0,
            total_files=len(ordered_files),
            message=(
                f"Smart Hybrid: focusing AI on {len(flagged_files)} files with SAST findings "
                f"+ {len(tier1_extra)} security-critical files "
                f"+ {len(neighbor_files)} context neighbors "
                f"(skipping {len(project_map['files']) - len(ordered_files)} clean files)"
            ),
        )
    else:
        # ai_only or hybrid with no SAST data — analyze all prioritized files
        ordered_files = tiers["tier1"] + tiers["tier2"]
        logger.info(
            "Scan %d: %d tier1 files, %d tier2 files, %d tier3 files (skipped)",
            scan_id, len(tiers["tier1"]), len(tiers["tier2"]), len(tiers["tier3"]),
        )

    # 7. Create chunks
    max_tokens = (model.context_window or 200000) - 40000  # Reserve for prompt + output
    max_tokens = min(max_tokens, 120000)  # Cap at 120K

    chunks = create_chunks(ordered_files, max_tokens_per_chunk=max_tokens)
    total_chunks = len(chunks)

    logger.info("Scan %d: created %d chunks for AI analysis", scan_id, total_chunks)

    # 8. Estimate total cost
    total_estimated_tokens = sum(
        sum(f.get("estimated_tokens", 0) for f in chunk) for chunk in chunks
    )
    est_cost = _calculate_cost(
        total_estimated_tokens,
        total_estimated_tokens // 4,  # rough output estimate
        model.input_price_per_mtok or 15.0,
        model.output_price_per_mtok or 75.0,
    )

    async with async_session() as session:
        await session.execute(
            update(Scan).where(Scan.id == scan_id).values(
                estimated_total_tokens=total_estimated_tokens,
                estimated_total_cost=est_cost,
                total_files=len(ordered_files),
            )
        )
        await session.commit()

    # 9. Process each chunk
    files_processed = 0

    # Throttling: calculate min delay between requests based on RPM limit
    rpm_limit = getattr(model, "requests_per_minute", None)
    min_delay_secs = (60.0 / rpm_limit) if rpm_limit and rpm_limit > 0 else 0.0
    last_request_time: float = 0.0

    if min_delay_secs > 0:
        logger.info(
            "Scan %d: throttling enabled — RPM limit %d → min %.1fs between requests",
            scan_id, rpm_limit, min_delay_secs,
        )

    for chunk_idx, chunk_files in enumerate(chunks):
        # Check budget before each chunk
        budget_status = await check_budget(scan_id, {
            "max_tokens_per_run": model.max_tokens_per_run,
            "max_budget_usd": model.max_budget_usd,
        })

        if budget_status.get("should_stop", False):
            logger.info(
                "Scan %d: budget exceeded at chunk %d/%d (tokens: %d, cost: $%.2f)",
                scan_id, chunk_idx + 1, total_chunks,
                budget_status.get("tokens_used", 0),
                budget_status.get("cost_used", 0),
            )

            await ws_manager.send_scan_progress(
                scan_id=scan_id,
                step_name="ai_analysis",
                status="budget_exceeded",
                files_processed=files_processed,
                total_files=len(ordered_files),
                tokens_used=total_tokens,
                cost_usd=total_cost,
                findings_count=len(all_findings),
                message=f"Budget exceeded. Analyzed {chunk_idx}/{total_chunks} chunks.",
            )
            break

        # Build context for this chunk
        chunk_context = await build_chunk_context(
            chunk_files,
            repo_path,
            sast_findings=sast_findings,
            chunk_index=chunk_idx,
            total_chunks=total_chunks,
        )

        # Broadcast progress
        await ws_manager.send_scan_progress(
            scan_id=scan_id,
            step_name="ai_analysis",
            status="running",
            files_processed=files_processed,
            total_files=len(ordered_files),
            tokens_used=total_tokens,
            cost_usd=total_cost,
            findings_count=len(all_findings),
            message=f"Analyzing chunk {chunk_idx + 1}/{total_chunks} ({len(chunk_files)} files)...",
        )

        # Throttle: wait if we're sending requests faster than the RPM limit allows
        if min_delay_secs > 0 and last_request_time > 0:
            elapsed = time.monotonic() - last_request_time
            wait = min_delay_secs - elapsed
            if wait > 0:
                logger.debug(
                    "Scan %d: throttle sleep %.1fs before chunk %d (RPM=%d)",
                    scan_id, wait, chunk_idx + 1, rpm_limit,
                )
                await ws_manager.send_scan_progress(
                    scan_id=scan_id,
                    step_name="ai_analysis",
                    status="running",
                    files_processed=files_processed,
                    total_files=len(ordered_files),
                    tokens_used=total_tokens,
                    cost_usd=total_cost,
                    findings_count=len(all_findings),
                    message=(
                        f"Throttling (RPM={rpm_limit}): waiting {wait:.0f}s before chunk "
                        f"{chunk_idx + 1}/{total_chunks}..."
                    ),
                )
                await asyncio.sleep(wait)

        # Call AI provider
        last_request_time = time.monotonic()
        try:
            response: AIResponse = await provider.analyze(
                system_prompt=system_prompt,
                user_prompt=chunk_context,
                model_id=model.model_id,
                max_output_tokens=8192,
                api_key=api_key,
                base_url=provider_record.base_url,
            )
        except Exception as e:
            logger.exception("AI API call failed for chunk %d: %s", chunk_idx, e)
            # Continue to next chunk on API error
            continue

        # Log token usage
        chunk_cost = _calculate_cost(
            response.input_tokens,
            response.output_tokens,
            model.input_price_per_mtok or 15.0,
            model.output_price_per_mtok or 75.0,
        )

        total_tokens += response.input_tokens + response.output_tokens
        total_cost += chunk_cost

        chunk_file_names = ", ".join(f["path"] for f in chunk_files[:5])
        if len(chunk_files) > 5:
            chunk_file_names += f" (+{len(chunk_files) - 5} more)"

        await log_usage(
            scan_id=scan_id,
            model_id=model.id,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            chunk_desc=f"Chunk {chunk_idx + 1}/{total_chunks}: {chunk_file_names}",
        )

        # Parse findings from AI response
        chunk_findings = _parse_ai_findings(response.content, tool_name="ai_analysis")

        if chunk_findings:
            all_findings.extend(chunk_findings)

            # Broadcast each finding
            for f in chunk_findings:
                await ws_manager.send_finding(scan_id, {
                    "title": f.title,
                    "severity": f.severity,
                    "type": f.type,
                    "file_path": f.file_path,
                    "tool_name": "ai_analysis",
                    "line_start": f.line_start,
                })

        files_processed += len(chunk_files)

        logger.info(
            "Scan %d chunk %d/%d: %d findings, %d tokens, $%.4f",
            scan_id, chunk_idx + 1, total_chunks,
            len(chunk_findings), response.input_tokens + response.output_tokens, chunk_cost,
        )

    # Update scan totals
    async with async_session() as session:
        await session.execute(
            update(Scan).where(Scan.id == scan_id).values(
                tokens_used=Scan.tokens_used + total_tokens,
                cost_usd=Scan.cost_usd + total_cost,
                files_processed=Scan.files_processed + files_processed,
            )
        )
        await session.commit()

    logger.info(
        "Scan %d AI analysis complete: %d findings, %d tokens, $%.2f",
        scan_id, len(all_findings), total_tokens, total_cost,
    )

    return all_findings, total_tokens, total_cost


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calculate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_mtok: float,
    output_price_per_mtok: float,
) -> float:
    """Calculate cost in USD from token counts and pricing."""
    input_cost = (input_tokens / 1_000_000) * input_price_per_mtok
    output_cost = (output_tokens / 1_000_000) * output_price_per_mtok
    return input_cost + output_cost

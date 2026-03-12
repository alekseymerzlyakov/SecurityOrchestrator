"""Code chunking strategy for sending repository code to AI in manageable pieces.

Handles:
- Building a project map (directory tree, file sizes, LOC estimates)
- Prioritizing files into tiers based on security relevance
- Splitting files into token-budget-aware chunks
- Building formatted context strings for each chunk
"""

import logging
import os
import re
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File extension filters
# ---------------------------------------------------------------------------
CODE_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".py", ".rb", ".java", ".go", ".rs", ".php",
    ".html", ".htm", ".vue", ".svelte",
    ".json", ".yaml", ".yml", ".toml", ".xml",
    ".css", ".scss", ".less",
    ".sh", ".bash",
    ".sql",
    ".env", ".env.example",
    ".config.js", ".config.ts",
}

SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg", "__pycache__", ".pytest_cache",
    "dist", "build", "coverage", ".next", ".nuxt", ".cache",
    "vendor", "venv", ".venv", "env", ".env",
    ".idea", ".vscode", ".DS_Store",
}

SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "composer.lock", "Gemfile.lock", "Cargo.lock",
    ".eslintcache",
}

MAX_FILE_SIZE_BYTES = 500_000  # Skip files larger than ~500KB

# ---------------------------------------------------------------------------
# Tier 1 (Critical) filename patterns
# ---------------------------------------------------------------------------
TIER1_PATTERNS = [
    re.compile(r"auth", re.IGNORECASE),
    re.compile(r"login", re.IGNORECASE),
    re.compile(r"session", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"cookie", re.IGNORECASE),
    re.compile(r"api[_\-/]", re.IGNORECASE),
    re.compile(r"websocket", re.IGNORECASE),
    re.compile(r"upload", re.IGNORECASE),
    re.compile(r"extension", re.IGNORECASE),
    re.compile(r"manifest", re.IGNORECASE),
    re.compile(r"middleware", re.IGNORECASE),
    re.compile(r"security", re.IGNORECASE),
    re.compile(r"crypto", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"permission", re.IGNORECASE),
    re.compile(r"cors", re.IGNORECASE),
    re.compile(r"csp", re.IGNORECASE),
]

# Content patterns that elevate a file to Tier 1
TIER1_CONTENT_PATTERNS = [
    re.compile(r"dangerouslySetInnerHTML"),
    re.compile(r"innerHTML\s*="),
    re.compile(r"eval\s*\("),
    re.compile(r"document\.write"),
    re.compile(r"window\.postMessage"),
    re.compile(r"addEventListener\s*\(\s*['\"]message['\"]"),
    re.compile(r"__html"),
    re.compile(r"subprocess|exec\s*\(|child_process"),
]

# ---------------------------------------------------------------------------
# Tier 2 (High) filename patterns
# ---------------------------------------------------------------------------
TIER2_PATTERNS = [
    re.compile(r"saga", re.IGNORECASE),
    re.compile(r"reducer", re.IGNORECASE),
    re.compile(r"route", re.IGNORECASE),
    re.compile(r"router", re.IGNORECASE),
    re.compile(r"form", re.IGNORECASE),
    re.compile(r"valid", re.IGNORECASE),
    re.compile(r"config", re.IGNORECASE),
    re.compile(r"store", re.IGNORECASE),
    re.compile(r"hook", re.IGNORECASE),
    re.compile(r"context", re.IGNORECASE),
    re.compile(r"service", re.IGNORECASE),
    re.compile(r"fetch", re.IGNORECASE),
    re.compile(r"request", re.IGNORECASE),
    re.compile(r"axios", re.IGNORECASE),
    re.compile(r"proxy", re.IGNORECASE),
    re.compile(r"nginx", re.IGNORECASE),
    re.compile(r"docker", re.IGNORECASE),
    re.compile(r"\.env", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Tier 3 (Low) filename patterns
# ---------------------------------------------------------------------------
TIER3_PATTERNS = [
    re.compile(r"\.test\.", re.IGNORECASE),
    re.compile(r"\.spec\.", re.IGNORECASE),
    re.compile(r"__tests__", re.IGNORECASE),
    re.compile(r"__mocks__", re.IGNORECASE),
    re.compile(r"\.stories\.", re.IGNORECASE),
    re.compile(r"\.style", re.IGNORECASE),
    re.compile(r"\.css$", re.IGNORECASE),
    re.compile(r"\.scss$", re.IGNORECASE),
    re.compile(r"\.less$", re.IGNORECASE),
    re.compile(r"\.snap$", re.IGNORECASE),
    re.compile(r"setupTests", re.IGNORECASE),
    re.compile(r"testUtils", re.IGNORECASE),
]


def _estimate_tokens(text: str) -> int:
    """Quick token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


def _is_code_file(path: Path) -> bool:
    """Check if a file has a recognized code extension."""
    return path.suffix.lower() in CODE_EXTENSIONS or path.name in {
        "Dockerfile", "Makefile", ".eslintrc", ".prettierrc",
        ".babelrc", "Procfile", ".htaccess",
    }


def _should_skip(path: Path) -> bool:
    """Check if path should be skipped."""
    parts = path.parts
    for part in parts:
        if part in SKIP_DIRS:
            return True
    if path.name in SKIP_FILES:
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def build_project_map(repo_path: str) -> dict:
    """Build a map of the project: directory tree, file sizes, LOC estimates.

    Returns:
        {
            "repo_path": str,
            "total_files": int,
            "total_lines": int,
            "total_size_bytes": int,
            "extensions": {".js": count, ...},
            "files": [
                {"path": "relative/path.js", "size": 1234, "lines": 50,
                 "estimated_tokens": 310, "extension": ".js"},
                ...
            ],
            "directory_tree": ["src/", "src/components/", ...],
        }
    """
    repo = Path(repo_path)
    if not repo.is_dir():
        raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

    files: list[dict] = []
    extensions: dict[str, int] = defaultdict(int)
    directories: set[str] = set()
    total_lines = 0
    total_size = 0

    for root, dirs, filenames in os.walk(repo):
        # Filter out skip directories in-place to prevent os.walk from descending
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        rel_dir = os.path.relpath(root, repo)
        if rel_dir != ".":
            directories.add(rel_dir + "/")

        for fname in filenames:
            full_path = Path(root) / fname
            rel_path = os.path.relpath(full_path, repo)

            if _should_skip(full_path):
                continue

            if not _is_code_file(full_path):
                continue

            try:
                stat = full_path.stat()
            except OSError:
                continue

            if stat.st_size > MAX_FILE_SIZE_BYTES:
                logger.debug("Skipping oversized file: %s (%d bytes)", rel_path, stat.st_size)
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            line_count = content.count("\n") + 1
            token_est = _estimate_tokens(content)
            ext = full_path.suffix.lower()

            files.append({
                "path": rel_path,
                "size": stat.st_size,
                "lines": line_count,
                "estimated_tokens": token_est,
                "extension": ext,
                "content": content,
            })

            extensions[ext] += 1
            total_lines += line_count
            total_size += stat.st_size

    # Sort by path for consistency
    files.sort(key=lambda f: f["path"])

    return {
        "repo_path": repo_path,
        "total_files": len(files),
        "total_lines": total_lines,
        "total_size_bytes": total_size,
        "extensions": dict(extensions),
        "files": files,
        "directory_tree": sorted(directories),
    }


def prioritize_files(
    file_map: list[dict],
    sast_findings: list | None = None,
) -> dict:
    """Assign files to priority tiers based on security relevance.

    Args:
        file_map: List of file dicts from build_project_map().
        sast_findings: Optional list of SAST findings with file_path keys.

    Returns:
        {"tier1": [...], "tier2": [...], "tier3": [...]}
        Each item is the original file dict with an added "tier" key.
    """
    # Build set of files that have SAST findings
    sast_files: set[str] = set()
    if sast_findings:
        for finding in sast_findings:
            fp = finding.get("file_path", "")
            if fp:
                sast_files.add(fp)

    tier1: list[dict] = []
    tier2: list[dict] = []
    tier3: list[dict] = []

    for file_info in file_map:
        path = file_info["path"]
        content = file_info.get("content", "")
        assigned = False

        # ---- Tier 1 checks ----
        # File has SAST findings
        if path in sast_files:
            file_info["tier"] = 1
            file_info["tier_reason"] = "SAST finding"
            tier1.append(file_info)
            continue

        # Filename matches critical patterns
        for pattern in TIER1_PATTERNS:
            if pattern.search(path):
                file_info["tier"] = 1
                file_info["tier_reason"] = f"filename matches: {pattern.pattern}"
                tier1.append(file_info)
                assigned = True
                break

        if assigned:
            continue

        # Content matches critical patterns
        for pattern in TIER1_CONTENT_PATTERNS:
            if pattern.search(content):
                file_info["tier"] = 1
                file_info["tier_reason"] = f"content matches: {pattern.pattern}"
                tier1.append(file_info)
                assigned = True
                break

        if assigned:
            continue

        # ---- Tier 3 checks (before Tier 2 since they are explicit exclusions) ----
        for pattern in TIER3_PATTERNS:
            if pattern.search(path):
                file_info["tier"] = 3
                file_info["tier_reason"] = f"low priority: {pattern.pattern}"
                tier3.append(file_info)
                assigned = True
                break

        if assigned:
            continue

        # ---- Tier 2 checks ----
        for pattern in TIER2_PATTERNS:
            if pattern.search(path):
                file_info["tier"] = 2
                file_info["tier_reason"] = f"filename matches: {pattern.pattern}"
                tier2.append(file_info)
                assigned = True
                break

        if assigned:
            continue

        # Default: Tier 2 (rather than Tier 3 — we err on the side of review)
        file_info["tier"] = 2
        file_info["tier_reason"] = "default"
        tier2.append(file_info)

    logger.info(
        "File prioritization: tier1=%d, tier2=%d, tier3=%d",
        len(tier1), len(tier2), len(tier3),
    )

    return {"tier1": tier1, "tier2": tier2, "tier3": tier3}


def create_chunks(
    files: list[dict],
    max_tokens_per_chunk: int = 120_000,
) -> list[list[dict]]:
    """Group files into chunks that fit within a token budget.

    Strategy:
    - Group related files (same directory) together when possible
    - Never split a single file across chunks
    - Respect max_tokens_per_chunk limit

    Args:
        files: List of file dicts (must include 'estimated_tokens' and 'path').
        max_tokens_per_chunk: Maximum estimated tokens per chunk.

    Returns:
        List of chunks. Each chunk is a list of
        {"path": str, "content": str, "estimated_tokens": int}.
    """
    if not files:
        return []

    # Group files by directory
    dir_groups: dict[str, list[dict]] = defaultdict(list)
    for f in files:
        directory = str(Path(f["path"]).parent)
        dir_groups[directory].append(f)

    chunks: list[list[dict]] = []
    current_chunk: list[dict] = []
    current_tokens = 0

    for directory in sorted(dir_groups.keys()):
        group_files = sorted(dir_groups[directory], key=lambda x: x["path"])

        for file_info in group_files:
            file_tokens = file_info.get("estimated_tokens", 0)

            # If a single file exceeds the budget, give it its own chunk
            if file_tokens > max_tokens_per_chunk:
                # Flush current chunk first
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_tokens = 0

                chunks.append([{
                    "path": file_info["path"],
                    "content": file_info.get("content", ""),
                    "estimated_tokens": file_tokens,
                }])
                logger.warning(
                    "File %s (%d tokens) exceeds chunk budget; placed in solo chunk.",
                    file_info["path"], file_tokens,
                )
                continue

            # If adding this file would exceed the budget, start a new chunk
            if current_tokens + file_tokens > max_tokens_per_chunk and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0

            current_chunk.append({
                "path": file_info["path"],
                "content": file_info.get("content", ""),
                "estimated_tokens": file_tokens,
            })
            current_tokens += file_tokens

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)

    logger.info(
        "Created %d chunks from %d files (max %d tokens/chunk).",
        len(chunks), len(files), max_tokens_per_chunk,
    )

    return chunks


async def build_chunk_context(
    chunk_files: list[dict],
    repo_path: str,
    sast_findings: list | None = None,
    chunk_index: int = 0,
    total_chunks: int = 1,
) -> str:
    """Build the full context string for a chunk to send to the AI.

    Args:
        chunk_files: List of file dicts in this chunk.
        repo_path: Root path of the repository.
        sast_findings: Optional SAST findings to include for context.
        chunk_index: Zero-based index of this chunk.
        total_chunks: Total number of chunks.

    Returns:
        Formatted context string with project info, file contents, and findings.
    """
    parts: list[str] = []

    # Header
    parts.append(f"## Security Analysis — Chunk {chunk_index + 1} of {total_chunks}")
    parts.append(f"Repository: {repo_path}")
    parts.append(f"Files in this chunk: {len(chunk_files)}")
    parts.append("")

    # File listing summary
    parts.append("### Files Included")
    total_tokens = 0
    for f in chunk_files:
        tokens = f.get("estimated_tokens", 0)
        total_tokens += tokens
        parts.append(f"- `{f['path']}` (~{tokens:,} tokens)")
    parts.append(f"\nTotal estimated tokens in chunk: ~{total_tokens:,}")
    parts.append("")

    # SAST findings for files in this chunk (if any)
    if sast_findings:
        chunk_paths = {f["path"] for f in chunk_files}
        relevant_findings = [
            finding for finding in sast_findings
            if finding.get("file_path", "") in chunk_paths
        ]

        if relevant_findings:
            parts.append("### SAST Tool Findings (for reference)")
            parts.append("The following findings were reported by automated SAST tools "
                         "for files in this chunk. Use these as hints but perform your "
                         "own independent analysis:")
            parts.append("")
            for finding in relevant_findings:
                parts.append(
                    f"- **{finding.get('tool_name', 'unknown')}** | "
                    f"{finding.get('severity', 'unknown')} | "
                    f"`{finding.get('file_path', '')}` line {finding.get('line_start', '?')}: "
                    f"{finding.get('title', finding.get('description', 'No description'))}"
                )
            parts.append("")

    # File contents
    parts.append("### Source Code")
    parts.append("")
    for f in chunk_files:
        parts.append(f"#### File: `{f['path']}`")
        parts.append("```")
        parts.append(f.get("content", ""))
        parts.append("```")
        parts.append("")

    return "\n".join(parts)

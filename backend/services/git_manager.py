"""Git operations service — async wrappers around git CLI commands."""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


async def _run_git(args: list[str], cwd: str, timeout: int = 60) -> str:
    """Run a git command and return stdout. Raises on non-zero exit."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"git {args[0]} timed out after {timeout}s")

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git {args[0]} failed (rc={proc.returncode}): {err_msg}")

    return stdout.decode(errors="replace")


async def list_branches(repo_path: str) -> list[dict]:
    """List all branches (local + remote).

    Returns a list of dicts with keys: name, is_remote, is_current.
    Also returns a flat dict with 'branches' and 'current' keys for
    backward compatibility with the projects router.
    """
    output = await _run_git(["branch", "-a"], cwd=repo_path)

    branches: list[dict] = []
    current_branch: str | None = None

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        is_current = line.startswith("* ")
        name = line.lstrip("* ").strip()

        # Skip HEAD pointers like "remotes/origin/HEAD -> origin/main"
        if "->" in name:
            continue

        is_remote = name.startswith("remotes/")
        display_name = name.removeprefix("remotes/").removeprefix("origin/") if is_remote else name

        if is_current:
            current_branch = display_name

        branches.append({
            "name": display_name,
            "is_remote": is_remote,
            "is_current": is_current,
        })

    # Deduplicate: if a local and remote branch share the same display name,
    # keep the local one and mark remote as duplicate.
    seen_local = {b["name"] for b in branches if not b["is_remote"]}
    branches = [
        b for b in branches
        if not (b["is_remote"] and b["name"] in seen_local)
    ]

    # The projects router expects {branches: [...], current: ...}
    # We return the list but also stash compat data via a small wrapper.
    # For callers that iterate, the list works directly.
    # For the router, we attach helper attributes.
    class BranchList(list):
        """List subclass that also exposes .get() for router compat."""
        def __init__(self, items, current=None, names=None):
            super().__init__(items)
            self._current = current
            self._names = names or []

        def get(self, key, default=None):
            if key == "branches":
                return self._names
            if key == "current":
                return self._current
            return default

    branch_names = [b["name"] for b in branches]
    return BranchList(branches, current=current_branch, names=branch_names)


async def get_file_tree(repo_path: str, branch: str = None) -> list[dict]:
    """List all tracked files with sizes and extensions.

    Returns list of {path, size_bytes, extension}.
    """
    args = ["ls-tree", "-r", "--name-only"]
    if branch:
        args.append(branch)
    else:
        args.append("HEAD")

    output = await _run_git(args, cwd=repo_path)

    file_tree: list[dict] = []
    for line in output.splitlines():
        file_path = line.strip()
        if not file_path:
            continue

        full_path = os.path.join(repo_path, file_path)
        try:
            size = os.path.getsize(full_path)
        except OSError:
            size = 0

        ext = Path(file_path).suffix.lower()
        file_tree.append({
            "path": file_path,
            "size_bytes": size,
            "extension": ext,
        })

    return file_tree


async def get_blame(repo_path: str, file_path: str) -> list[dict]:
    """Run git blame --line-porcelain and parse results.

    Returns list of {line, author, date, commit} for each line.
    """
    output = await _run_git(
        ["blame", "--line-porcelain", file_path],
        cwd=repo_path,
        timeout=120,
    )

    results: list[dict] = []
    current: dict = {}
    line_number = 0

    for raw_line in output.splitlines():
        if raw_line.startswith("\t"):
            # This is the actual source line content
            line_number += 1
            current["line"] = line_number
            current["content"] = raw_line[1:]  # strip leading tab
            results.append(current)
            current = {}
        elif raw_line.startswith("author "):
            current["author"] = raw_line[len("author "):]
        elif raw_line.startswith("author-time "):
            try:
                ts = int(raw_line[len("author-time "):])
                current["date"] = datetime.utcfromtimestamp(ts).isoformat()
            except (ValueError, OSError):
                current["date"] = ""
        elif len(raw_line) >= 40 and raw_line[0].isalnum() and " " in raw_line:
            # First line of a blame block: <sha> <orig_line> <final_line> [<num_lines>]
            parts = raw_line.split()
            if len(parts[0]) == 40:
                current["commit"] = parts[0]

    return results


async def get_diff(repo_path: str, branch1: str, branch2: str) -> str:
    """Get the diff between two branches."""
    return await _run_git(["diff", f"{branch1}..{branch2}"], cwd=repo_path, timeout=120)


async def get_commit_authors(repo_path: str) -> list[dict]:
    """Get list of commit authors with email and commit count.

    Returns list of {name, email, commits}.
    Also returns a flat list of "Name <email>" strings for router compat.
    """
    output = await _run_git(["shortlog", "-sne", "HEAD"], cwd=repo_path)

    authors: list[dict] = []
    author_strings: list[str] = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: "  123\tJohn Doe <john@example.com>"
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue

        try:
            commits = int(parts[0].strip())
        except ValueError:
            commits = 0

        author_str = parts[1].strip()
        author_strings.append(author_str)

        # Parse "Name <email>"
        name = author_str
        email = ""
        if "<" in author_str and author_str.endswith(">"):
            idx = author_str.index("<")
            name = author_str[:idx].strip()
            email = author_str[idx + 1:-1]

        authors.append({
            "name": name,
            "email": email,
            "commits": commits,
        })

    # Router compat: the projects router expects a flat list of strings
    class AuthorList(list):
        pass

    result = AuthorList(author_strings)
    result.details = authors
    return result


async def get_file_content(repo_path: str, file_path: str) -> str:
    """Read file content from the working directory."""
    full_path = os.path.join(repo_path, file_path)
    if not os.path.isfile(full_path):
        raise FileNotFoundError(f"File not found: {full_path}")

    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(None, _read_file, full_path)
    return content


def _read_file(path: str) -> str:
    """Synchronous file reader (run in executor)."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

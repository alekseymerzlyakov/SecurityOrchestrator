"""Abstract base class for security tool runners."""

import asyncio
import logging
import os
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Project root for finding venv binaries
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # SecurityTesting/
_VENV_BIN = _PROJECT_ROOT / "venv" / "bin"


@dataclass
class ToolFinding:
    """Standardized finding from any security tool."""

    title: str
    description: str = ""
    severity: str = "medium"  # critical, high, medium, low, info
    type: str = ""  # xss, injection, secret, dependency, auth, config, etc.
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    code_snippet: str = ""
    confidence: str = "medium"  # high, medium, low
    cwe_id: str = ""
    tool_name: str = ""
    recommendation: str = ""
    metadata: dict = field(default_factory=dict)


def _find_binary(name: str) -> str | None:
    """Find a binary on PATH or in the project venv."""
    # First check system PATH
    system_path = shutil.which(name)
    if system_path:
        return system_path
    # Then check our venv
    venv_path = _VENV_BIN / name
    if venv_path.exists() and os.access(venv_path, os.X_OK):
        return str(venv_path)
    return None


# Type for async progress callback: on_progress(message: str, count: int)
ProgressCallback = Callable[[str, int], Coroutine[Any, Any, None]]


class BaseToolRunner(ABC):
    """Base class all tool runners must inherit from."""

    name: str = ""
    binary_name: str = ""  # Name of the CLI binary to check

    @abstractmethod
    async def run(
        self,
        repo_path: str,
        config: dict = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[ToolFinding]:
        """Execute the tool and return normalized findings."""
        pass

    def _resolve_binary(self) -> str | None:
        """Resolve the full path to the tool binary."""
        if not self.binary_name:
            return None
        return _find_binary(self.binary_name)

    async def is_installed(self) -> bool:
        """Check if the tool binary is available on PATH or in venv."""
        return self._resolve_binary() is not None

    async def get_version(self) -> str:
        """Get the tool version string. Override in subclasses for custom logic."""
        binary = self._resolve_binary()
        if not binary:
            return "unknown"
        try:
            stdout, _, rc = await self._run_command(
                [binary, "--version"]
            )
            if rc == 0:
                return stdout.strip().split("\n")[0]
        except Exception:
            pass
        return "unknown"

    def _resolve_cmd(self, cmd: list[str]) -> list[str]:
        """Resolve the first element of cmd to a full binary path if needed."""
        if not cmd:
            return cmd
        binary = _find_binary(cmd[0])
        if binary and binary != cmd[0]:
            return [binary] + cmd[1:]
        return cmd

    async def _run_command(
        self,
        cmd: list[str],
        cwd: str = None,
        timeout: int = 600,
        env: dict = None,
    ) -> tuple[str, str, int]:
        """Run a subprocess command and return (stdout, stderr, returncode).

        Automatically resolves binary names to full paths (system PATH or venv).
        Does NOT raise on non-zero return code — callers decide how to handle.
        """
        cmd = self._resolve_cmd(cmd)

        run_env = os.environ.copy()
        # Ensure venv bin is in PATH for child processes
        venv_bin_str = str(_VENV_BIN)
        if venv_bin_str not in run_env.get("PATH", ""):
            run_env["PATH"] = f"{venv_bin_str}:{run_env.get('PATH', '')}"
        if env:
            run_env.update(env)

        logger.debug("Running command: %s (cwd=%s)", " ".join(cmd), cwd)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=run_env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.warning("Command timed out after %ds: %s", timeout, " ".join(cmd))
            return "", f"Command timed out after {timeout}s", -1

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        return stdout, stderr, proc.returncode

    async def _run_command_streaming(
        self,
        cmd: list[str],
        cwd: str = None,
        timeout: int = 600,
        env: dict = None,
        on_line: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> tuple[str, str, int]:
        """Run a subprocess and call on_line(line) for each stdout line as it arrives.

        Returns (full_stdout, full_stderr, returncode) — same contract as _run_command.
        on_line is an async callback called with each decoded line (strip applied).
        """
        cmd = self._resolve_cmd(cmd)

        run_env = os.environ.copy()
        venv_bin_str = str(_VENV_BIN)
        if venv_bin_str not in run_env.get("PATH", ""):
            run_env["PATH"] = f"{venv_bin_str}:{run_env.get('PATH', '')}"
        if env:
            run_env.update(env)

        logger.debug("Running streaming command: %s (cwd=%s)", " ".join(cmd), cwd)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=run_env,
        )

        stdout_lines: list[str] = []
        stderr_task_done = asyncio.Event()
        stderr_buf: list[bytes] = []

        async def _read_stderr():
            assert proc.stderr is not None
            data = await proc.stderr.read()
            stderr_buf.append(data)
            stderr_task_done.set()

        asyncio.ensure_future(_read_stderr())

        try:
            deadline = asyncio.get_event_loop().time() + timeout
            assert proc.stdout is not None
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    proc.kill()
                    logger.warning("Streaming command timed out: %s", " ".join(cmd))
                    break
                try:
                    line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=min(remaining, 30))
                except asyncio.TimeoutError:
                    continue
                if not line_bytes:
                    break  # EOF
                line = line_bytes.decode(errors="replace")
                stdout_lines.append(line)
                if on_line:
                    try:
                        await on_line(line.rstrip("\n"))
                    except Exception as cb_exc:
                        logger.debug("on_line callback error: %s", cb_exc)
        finally:
            await asyncio.wait_for(asyncio.shield(stderr_task_done.wait()), timeout=5.0)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()

        full_stdout = "".join(stdout_lines)
        full_stderr = stderr_buf[0].decode(errors="replace") if stderr_buf else ""
        return full_stdout, full_stderr, proc.returncode or 0

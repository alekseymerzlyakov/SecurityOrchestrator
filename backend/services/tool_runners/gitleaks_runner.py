"""Gitleaks secret scanner runner."""

import json
import logging
import os
import tempfile

from backend.services.tool_runners.base import BaseToolRunner, ProgressCallback, ToolFinding

logger = logging.getLogger(__name__)


class GitleaksRunner(BaseToolRunner):
    name = "gitleaks"
    binary_name = "gitleaks"

    async def run(
        self,
        repo_path: str,
        config: dict = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[ToolFinding]:
        config = config or {}

        if on_progress:
            await on_progress("Сканируем git историю на секреты...", 0)

        # Use a temp file for the report since /dev/stdout may not be writable
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            report_path = tmp.name

        try:
            cmd = [
                "gitleaks",
                "detect",
                "--source", repo_path,
                "--report-format", "json",
                "--report-path", report_path,
                "--no-banner",
            ]

            # Optional: add custom config file
            config_path = config.get("config_path")
            if config_path:
                cmd.extend(["--config", config_path])

            _stdout, stderr, rc = await self._run_command(cmd, cwd=repo_path)

            # gitleaks returns exit code 1 when leaks are found, 0 when clean
            if rc not in (0, 1):
                logger.error("Gitleaks failed (rc=%d): %s", rc, stderr)
                return []

            # Read the report file
            try:
                with open(report_path, "r") as f:
                    report_content = f.read()
            except FileNotFoundError:
                logger.warning("Gitleaks report file not found at %s", report_path)
                return []

            if rc == 0 and not report_content.strip():
                logger.info("Gitleaks: no secrets detected")
                if on_progress:
                    await on_progress("Секретов не найдено", 0)
                return []

            findings = self._parse_output(report_content)
            if on_progress:
                await on_progress(f"Готово — найдено {len(findings)} секретов", len(findings))
            return findings
        finally:
            # Clean up temp file
            try:
                os.unlink(report_path)
            except OSError:
                pass

    def _parse_output(self, raw_json: str) -> list[ToolFinding]:
        """Parse gitleaks JSON output into ToolFinding objects."""
        findings: list[ToolFinding] = []

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse gitleaks JSON: %s", e)
            return findings

        if not isinstance(data, list):
            logger.warning("Unexpected gitleaks output format: expected list")
            return findings

        for leak in data:
            rule_id = leak.get("RuleID", "unknown-secret")
            description = leak.get("Description", "Potential secret detected")
            file_path = leak.get("File", "")
            line = leak.get("StartLine", 0)
            line_end = leak.get("EndLine", line)
            match = leak.get("Match", "")
            secret = leak.get("Secret", "")
            commit = leak.get("Commit", "")
            author = leak.get("Author", "")
            date = leak.get("Date", "")

            # Mask the secret in code snippet for safety
            masked_match = match
            if secret and len(secret) > 4:
                masked_match = match.replace(secret, secret[:2] + "***" + secret[-2:])
            elif secret:
                masked_match = match.replace(secret, "***")

            findings.append(ToolFinding(
                title=f"Secret detected: {rule_id}",
                description=description,
                severity="high",
                type="secret",
                file_path=file_path,
                line_start=line,
                line_end=line_end,
                code_snippet=masked_match,
                confidence="high",
                cwe_id="CWE-798",  # Use of Hard-coded Credentials
                tool_name="gitleaks",
                recommendation=(
                    "Remove the secret from the codebase and rotate the credential. "
                    "Consider using environment variables or a secrets manager."
                ),
                metadata={
                    "rule_id": rule_id,
                    "commit": commit,
                    "author": author,
                    "date": date,
                    "entropy": leak.get("Entropy", 0),
                },
            ))

        logger.info("Gitleaks found %d secrets", len(findings))
        return findings

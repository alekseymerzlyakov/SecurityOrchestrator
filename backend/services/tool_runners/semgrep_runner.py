"""Semgrep SAST scanner runner."""

import json
import logging
import os

from backend.services.tool_runners.base import BaseToolRunner, ProgressCallback, ToolFinding

logger = logging.getLogger(__name__)

# Map semgrep severity → our normalized severity
SEVERITY_MAP = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}


class SemgrepRunner(BaseToolRunner):
    name = "semgrep"
    binary_name = "semgrep"

    async def run(
        self,
        repo_path: str,
        config: dict = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[ToolFinding]:
        config = config or {}
        rules = config.get("rules", "auto")

        # Build scan target: prefer packages/ subdirectory if it exists
        scan_target = repo_path
        packages_dir = os.path.join(repo_path, "packages")
        if os.path.isdir(packages_dir):
            scan_target = packages_dir

        cmd = [
            "semgrep",
            "--config", rules,
            "--json",
            "--quiet",
            scan_target,
        ]

        if on_progress:
            await on_progress("Запускаем semgrep --config auto...", 0)

        stdout, stderr, rc = await self._run_command(cmd, cwd=repo_path, timeout=600)

        if rc != 0 and not stdout:
            logger.error("Semgrep failed (rc=%d): %s", rc, stderr)
            return []

        findings = self._parse_output(stdout, repo_path)
        if on_progress:
            await on_progress(f"Готово — найдено {len(findings)} issues", len(findings))
        return findings

    def _parse_output(self, raw_json: str, repo_path: str) -> list[ToolFinding]:
        """Parse semgrep JSON output into ToolFinding objects."""
        findings: list[ToolFinding] = []

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse semgrep JSON: %s", e)
            return findings

        results = data.get("results", [])

        for result in results:
            check_id = result.get("check_id", "unknown-rule")
            extra = result.get("extra", {})
            severity_raw = extra.get("severity", "WARNING").upper()
            severity = SEVERITY_MAP.get(severity_raw, "medium")

            message = extra.get("message", "")
            metadata = extra.get("metadata", {})
            cwe_list = metadata.get("cwe", [])
            cwe_id = cwe_list[0] if isinstance(cwe_list, list) and cwe_list else ""
            if isinstance(cwe_id, str) and "CWE-" in cwe_id:
                # Extract just the CWE number, e.g., "CWE-79: ..." -> "CWE-79"
                cwe_id = cwe_id.split(":")[0].strip()

            # File path relative to repo
            file_path = result.get("path", "")
            if file_path.startswith(repo_path):
                file_path = os.path.relpath(file_path, repo_path)

            start = result.get("start", {})
            end = result.get("end", {})
            line_start = start.get("line", 0)
            line_end = end.get("line", 0)

            # Code snippet from the matched lines
            code_snippet = extra.get("lines", "").strip()

            confidence = metadata.get("confidence", "MEDIUM").lower()
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"

            finding_type = self._infer_type(check_id, message)

            findings.append(ToolFinding(
                title=check_id,
                description=message,
                severity=severity,
                type=finding_type,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                code_snippet=code_snippet,
                confidence=confidence,
                cwe_id=cwe_id,
                tool_name="semgrep",
                recommendation=metadata.get("fix", ""),
                metadata={
                    "rule_url": metadata.get("source", ""),
                    "owasp": metadata.get("owasp", []),
                },
            ))

        logger.info("Semgrep found %d issues", len(findings))
        return findings

    @staticmethod
    def _infer_type(check_id: str, message: str) -> str:
        """Attempt to infer finding type from rule ID and message."""
        text = f"{check_id} {message}".lower()
        if "xss" in text or "cross-site" in text:
            return "xss"
        if "inject" in text or "sqli" in text:
            return "injection"
        if "auth" in text:
            return "auth"
        if "crypto" in text or "cipher" in text or "hash" in text:
            return "crypto"
        if "secret" in text or "password" in text or "credential" in text:
            return "secret"
        if "config" in text:
            return "config"
        if "deserializ" in text:
            return "deserialization"
        if "path-traversal" in text or "directory" in text:
            return "path_traversal"
        return "code_quality"

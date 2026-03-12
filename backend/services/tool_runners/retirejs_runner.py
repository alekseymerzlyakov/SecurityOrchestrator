"""RetireJS vulnerable JavaScript library scanner runner."""

import json
import logging
import os

from backend.services.tool_runners.base import BaseToolRunner, ProgressCallback, ToolFinding

logger = logging.getLogger(__name__)

# Map RetireJS severity → our normalized severity
SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "none": "info",
}


class RetireJSRunner(BaseToolRunner):
    name = "retirejs"
    binary_name = "retire"

    async def run(
        self,
        repo_path: str,
        config: dict = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[ToolFinding]:
        config = config or {}

        if on_progress:
            await on_progress("Сканируем JS библиотеки на известные уязвимости...", 0)

        # Find the best scan target — retire needs a directory with node_modules.
        # Walk up to 3 levels to find node_modules; prefer root, then subdirs.
        scan_target = self._find_scan_target(repo_path)
        if not scan_target:
            logger.info("RetireJS: no node_modules found under %s, skipping", repo_path)
            if on_progress:
                await on_progress("node_modules не найдены — пропускаем", 0)
            return []

        cmd = [
            "retire",
            "--outputformat", "json",
            "--path", scan_target,
        ]

        # Optional: severity threshold
        severity_level = config.get("severity", "low")
        cmd.extend(["--severity", severity_level])

        # Optional: ignore specific paths
        ignore_paths = config.get("ignore_paths", [])
        for path in ignore_paths:
            cmd.extend(["--ignore", path])

        stdout, stderr, rc = await self._run_command(cmd, cwd=repo_path)

        # RetireJS returns exit code 13 when vulnerabilities are found
        if rc not in (0, 13) and not stdout:
            # RetireJS sometimes outputs to stderr instead of stdout
            if stderr and (stderr.strip().startswith("[") or stderr.strip().startswith("{")):
                stdout = stderr
            else:
                logger.error("RetireJS failed (rc=%d): %s", rc, stderr)
                return []

        if not stdout or not stdout.strip():
            logger.info("RetireJS: no vulnerable libraries found")
            if on_progress:
                await on_progress("Уязвимых библиотек не найдено", 0)
            return []

        findings = self._parse_output(stdout, repo_path)
        if on_progress:
            await on_progress(f"Готово — найдено {len(findings)} уязвимых библиотек", len(findings))
        return findings

    @staticmethod
    def _find_scan_target(repo_path: str) -> str | None:
        """Find the best directory to pass to retire --path.

        retire scans JS files and node_modules for known vulnerable libraries.
        We look for node_modules up to 3 directory levels deep.
        Returns the shallowest parent directory that contains node_modules,
        or None if none found.
        """
        # Check root first
        if os.path.isdir(os.path.join(repo_path, "node_modules")):
            return repo_path

        # Walk one level deep (e.g. frontend/, packages/)
        try:
            for entry in os.scandir(repo_path):
                if not entry.is_dir() or entry.name.startswith('.'):
                    continue
                if os.path.isdir(os.path.join(entry.path, "node_modules")):
                    return entry.path
        except OSError:
            pass

        # Walk two levels deep (e.g. packages/app/)
        try:
            for entry in os.scandir(repo_path):
                if not entry.is_dir() or entry.name.startswith('.'):
                    continue
                for sub in os.scandir(entry.path):
                    if not sub.is_dir() or sub.name.startswith('.'):
                        continue
                    if os.path.isdir(os.path.join(sub.path, "node_modules")):
                        return sub.path
        except OSError:
            pass

        return None

    def _parse_output(self, raw_json: str, repo_path: str) -> list[ToolFinding]:
        """Parse RetireJS JSON output into ToolFinding objects."""
        findings: list[ToolFinding] = []

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse RetireJS JSON: %s", e)
            return findings

        if not isinstance(data, list):
            # Some versions wrap in { "data": [...] }
            data = data.get("data", []) if isinstance(data, dict) else []

        for entry in data:
            file_path = entry.get("file", "")
            if file_path.startswith(repo_path):
                file_path = os.path.relpath(file_path, repo_path)

            results = entry.get("results", [])

            for result in results:
                component = result.get("component", "unknown")
                version = result.get("version", "unknown")
                vulnerabilities = result.get("vulnerabilities", [])

                for vuln in vulnerabilities:
                    severity_raw = vuln.get("severity", "medium").lower()
                    severity = SEVERITY_MAP.get(severity_raw, "medium")

                    # Gather advisory info
                    info_list = vuln.get("info", [])
                    identifiers = vuln.get("identifiers", {})
                    cve_list = identifiers.get("CVE", [])
                    issue_id = identifiers.get("issue", "")
                    summary = identifiers.get("summary", "")
                    bug = identifiers.get("bug", "")

                    # Build a descriptive title
                    cve_str = cve_list[0] if cve_list else ""
                    if summary:
                        title = f"{component}@{version}: {summary}"
                    elif cve_str:
                        title = f"{cve_str} in {component}@{version}"
                    else:
                        title = f"Vulnerable library: {component}@{version}"

                    # Build description from available info
                    description_parts = []
                    if summary:
                        description_parts.append(summary)
                    if cve_list:
                        description_parts.append(f"CVEs: {', '.join(cve_list)}")
                    if info_list:
                        description_parts.append(f"References: {', '.join(info_list[:3])}")
                    description = ". ".join(description_parts) if description_parts else (
                        f"Known vulnerability in {component} version {version}."
                    )

                    # Map CVE to CWE if available (RetireJS doesn't usually provide CWE)
                    at_or_above = vuln.get("atOrAbove", "")
                    below = vuln.get("below", "")
                    fix_version = below if below else ""

                    recommendation = ""
                    if fix_version:
                        recommendation = f"Upgrade {component} to version {fix_version} or later."
                    else:
                        recommendation = (
                            f"Upgrade {component} to the latest version. "
                            "Check the project's release notes for security patches."
                        )

                    findings.append(ToolFinding(
                        title=title,
                        description=description,
                        severity=severity,
                        type="dependency",
                        file_path=file_path,
                        line_start=0,
                        line_end=0,
                        code_snippet=f"{component}@{version}",
                        confidence="high",
                        cwe_id="",
                        tool_name="retirejs",
                        recommendation=recommendation,
                        metadata={
                            "component": component,
                            "version": version,
                            "cves": cve_list,
                            "info_urls": info_list,
                            "issue": issue_id,
                            "bug": bug,
                            "at_or_above": at_or_above,
                            "below": below,
                        },
                    ))

        logger.info("RetireJS found %d vulnerable libraries", len(findings))
        return findings

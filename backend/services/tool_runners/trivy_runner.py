"""Trivy dependency vulnerability scanner runner."""

import json
import logging

from backend.services.tool_runners.base import BaseToolRunner, ProgressCallback, ToolFinding

logger = logging.getLogger(__name__)

# Map trivy severity → our normalized severity
SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "UNKNOWN": "info",
}


class TrivyRunner(BaseToolRunner):
    name = "trivy"
    binary_name = "trivy"

    async def run(
        self,
        repo_path: str,
        config: dict = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[ToolFinding]:
        config = config or {}
        scan_type = config.get("scan_type", "fs")

        cmd = [
            "trivy",
            scan_type,
            "--format", "json",
            "--quiet",
            repo_path,
        ]

        # Optional severity filter
        severity_filter = config.get("severity")
        if severity_filter:
            cmd.extend(["--severity", severity_filter])

        if on_progress:
            await on_progress("Сканируем зависимости на CVE...", 0)

        # First attempt: run normally
        stdout, stderr, rc = await self._run_command(cmd, cwd=repo_path)

        # If Docker credential helper fails, retry with workaround env
        if rc != 0 and "docker-credential" in stderr:
            logger.warning("Trivy: Docker credential helper issue detected, retrying with DOCKER_CONFIG workaround")
            import tempfile, json as _json, os as _os
            # Create a temp Docker config without credsStore
            with tempfile.TemporaryDirectory() as tmpdir:
                docker_cfg_path = _os.path.expanduser("~/.docker/config.json")
                temp_cfg = {}
                if _os.path.exists(docker_cfg_path):
                    try:
                        with open(docker_cfg_path) as f:
                            temp_cfg = _json.load(f)
                    except Exception:
                        pass
                temp_cfg.pop("credsStore", None)
                temp_docker_cfg = _os.path.join(tmpdir, "config.json")
                with open(temp_docker_cfg, "w") as f:
                    _json.dump(temp_cfg, f)
                stdout, stderr, rc = await self._run_command(
                    cmd, cwd=repo_path, env={"DOCKER_CONFIG": tmpdir}
                )

        if rc != 0 and not stdout:
            logger.error("Trivy failed (rc=%d): %s", rc, stderr)
            return []

        findings = self._parse_output(stdout)
        if on_progress:
            await on_progress(f"Готово — найдено {len(findings)} CVE", len(findings))
        return findings

    def _parse_output(self, raw_json: str) -> list[ToolFinding]:
        """Parse trivy JSON output into ToolFinding objects."""
        findings: list[ToolFinding] = []

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse trivy JSON: %s", e)
            return findings

        # Trivy output has a "Results" array, each with "Vulnerabilities"
        results = data.get("Results", [])

        for result in results:
            target = result.get("Target", "")
            result_type = result.get("Type", "")
            vulns = result.get("Vulnerabilities") or []

            for vuln in vulns:
                vuln_id = vuln.get("VulnerabilityID", "")
                pkg_name = vuln.get("PkgName", "")
                installed_ver = vuln.get("InstalledVersion", "")
                fixed_ver = vuln.get("FixedVersion", "")
                severity_raw = vuln.get("Severity", "UNKNOWN").upper()
                severity = SEVERITY_MAP.get(severity_raw, "info")
                title_str = vuln.get("Title", "")
                description = vuln.get("Description", "")

                # Build a human-readable title
                if title_str:
                    title = f"{vuln_id}: {title_str}"
                else:
                    title = f"{vuln_id} in {pkg_name}@{installed_ver}"

                # Build recommendation
                recommendation = ""
                if fixed_ver:
                    recommendation = f"Upgrade {pkg_name} from {installed_ver} to {fixed_ver}."
                else:
                    recommendation = f"No fix available yet for {pkg_name}@{installed_ver}. Monitor for updates."

                # Extract CWE IDs
                cwe_ids = vuln.get("CweIDs") or []
                # CweIDs is a list — join to single string for TEXT column
                cwe_id = ", ".join(str(c) for c in cwe_ids) if cwe_ids else ""

                # CVSS score
                cvss_data = vuln.get("CVSS", {})
                cvss_score = None
                for source_data in cvss_data.values():
                    if isinstance(source_data, dict) and "V3Score" in source_data:
                        cvss_score = source_data["V3Score"]
                        break

                findings.append(ToolFinding(
                    title=title,
                    description=description,
                    severity=severity,
                    type="dependency",
                    file_path=target,
                    line_start=0,
                    line_end=0,
                    code_snippet=f"{pkg_name}@{installed_ver}",
                    confidence="high",
                    cwe_id=cwe_id,
                    tool_name="trivy",
                    recommendation=recommendation,
                    metadata={
                        "vuln_id": vuln_id,
                        "package": pkg_name,
                        "installed_version": installed_ver,
                        "fixed_version": fixed_ver,
                        "pkg_type": result_type,
                        "cvss_score": cvss_score,
                        "references": vuln.get("References", []),
                    },
                ))

        logger.info("Trivy found %d vulnerabilities", len(findings))
        return findings

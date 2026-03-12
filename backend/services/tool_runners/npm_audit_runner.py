"""npm audit runner for dependency vulnerability scanning."""

import json
import logging
import os

from backend.services.tool_runners.base import BaseToolRunner, ToolFinding


def _normalize_cwe(cwe_raw) -> str:
    """Normalize CWE value to a plain string for DB storage.

    npm audit can return:
      - str:  "CWE-79"
      - list: ["CWE-915", "CWE-1321"]  ← crashes SQLite TEXT column
      - nested list: [["CWE-79"]]
    We join multiple CWEs with ", " so nothing is lost.
    """
    if not cwe_raw:
        return ""
    if isinstance(cwe_raw, str):
        return cwe_raw
    if isinstance(cwe_raw, list):
        flat: list[str] = []
        for item in cwe_raw:
            if isinstance(item, list):
                flat.extend(str(i) for i in item if i)
            elif item:
                flat.append(str(item))
        return ", ".join(flat)
    return str(cwe_raw)

logger = logging.getLogger(__name__)

# Map npm severity → our normalized severity
SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "moderate": "medium",
    "low": "low",
    "info": "info",
}


class NpmAuditRunner(BaseToolRunner):
    name = "npm_audit"
    binary_name = "npm"

    async def run(
        self,
        repo_path: str,
        config: dict = None,
        on_progress=None,
    ) -> list[ToolFinding]:
        config = config or {}

        has_package = os.path.isfile(os.path.join(repo_path, "package.json"))
        if not has_package:
            logger.info("No package.json found in %s, skipping npm audit", repo_path)
            return []

        has_npm_lock = os.path.isfile(os.path.join(repo_path, "package-lock.json"))
        has_yarn_lock = os.path.isfile(os.path.join(repo_path, "yarn.lock"))
        has_pnpm_lock = os.path.isfile(os.path.join(repo_path, "pnpm-lock.yaml"))

        if has_yarn_lock:
            return await self._run_yarn_audit(repo_path, on_progress)

        if has_pnpm_lock:
            if on_progress:
                await on_progress("Fetching pnpm advisories...", 0)
            cmd = ["pnpm", "audit", "--json"]
            stdout, stderr, rc = await self._run_command(cmd, cwd=repo_path)
            if stdout:
                findings = self._parse_output(stdout)
                if on_progress:
                    await on_progress(f"Done — {len(findings)} vulnerabilities", len(findings))
                return findings
            return []

        # npm — needs package-lock.json; if missing try to generate it
        if not has_npm_lock:
            if on_progress:
                await on_progress("Generating package-lock.json...", 0)
            logger.info("No lockfile found, generating package-lock.json with npm i --package-lock-only")
            _, _, rc2 = await self._run_command(
                ["npm", "i", "--package-lock-only", "--ignore-scripts"], cwd=repo_path
            )
            if rc2 != 0:
                logger.warning("Could not generate package-lock.json (rc=%d), skipping npm audit", rc2)
                return []

        if on_progress:
            await on_progress("Fetching npm advisories...", 0)

        cmd = ["npm", "audit", "--json"]
        audit_level = config.get("audit_level")
        if audit_level:
            cmd.extend(["--audit-level", audit_level])
        if config.get("production_only", False):
            cmd.append("--omit=dev")

        stdout, stderr, rc = await self._run_command(cmd, cwd=repo_path)

        if not stdout:
            if rc != 0:
                logger.error("npm audit failed (rc=%d): %s", rc, stderr)
            else:
                logger.info("npm audit: no vulnerabilities found")
            return []

        findings = self._parse_output(stdout)
        if on_progress:
            await on_progress(f"Done — {len(findings)} vulnerabilities found", len(findings))
        return findings

    async def _run_yarn_audit(self, repo_path: str, on_progress=None) -> list[ToolFinding]:
        """Run yarn audit with streaming progress — yarn outputs NDJSON line by line."""
        lines: list[str] = []
        # Track unique advisory IDs in real-time — same dedup as _parse_yarn_output
        seen_advisory_ids: set = set()

        if on_progress:
            await on_progress("Подключаемся к yarn audit registry...", 0)

        async def on_line(line: str):
            lines.append(line)
            if not line.strip():
                return
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return
            if obj.get("type") == "auditAdvisory":
                adv = obj.get("data", {}).get("advisory", {})
                adv_id = adv.get("id")
                # Only count each unique advisory once (same logic as parse)
                if adv_id and adv_id not in seen_advisory_ids:
                    seen_advisory_ids.add(adv_id)
                    pkg = adv.get("module_name", "")
                    sev = adv.get("severity", "")
                    unique_count = len(seen_advisory_ids)
                    if on_progress:
                        await on_progress(
                            f"Сканируем пакеты… {unique_count} уникальных уязвимостей"
                            + (f" (последняя: {sev} в {pkg})" if pkg else ""),
                            unique_count,
                        )
            elif obj.get("type") == "auditSummary":
                data = obj.get("data", {})
                total = data.get("totalDependencies", 0)
                unique_count = len(seen_advisory_ids)
                if on_progress and total:
                    await on_progress(
                        f"Проверено {total} зависимостей, {unique_count} уникальных уязвимостей",
                        unique_count,
                    )

        stdout, stderr, rc = await self._run_command_streaming(
            ["yarn", "audit", "--json"],
            cwd=repo_path,
            on_line=on_line,
        )

        full_output = "\n".join(lines) if lines else stdout
        if not full_output.strip():
            logger.info("yarn audit: no output (rc=%d) %s", rc, stderr[:200] if stderr else "")
            return []

        findings = self._parse_yarn_output(full_output)
        if on_progress:
            await on_progress(f"Готово — {len(findings)} уникальных уязвимостей", len(findings))
        return findings

    def _parse_yarn_output(self, raw: str) -> list[ToolFinding]:
        """Parse yarn audit NDJSON output (one JSON per line)."""
        findings: list[ToolFinding] = []
        seen_ids: set = set()
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "auditAdvisory":
                continue
            adv = obj.get("data", {}).get("advisory", {})
            if not adv:
                continue
            adv_id = adv.get("id")
            if adv_id in seen_ids:
                continue
            seen_ids.add(adv_id)

            module_name = adv.get("module_name", "")
            severity_raw = adv.get("severity", "info").lower()
            severity = SEVERITY_MAP.get(severity_raw, "info")
            title = adv.get("title", f"Vulnerability in {module_name}")
            overview = adv.get("overview", "")
            recommendation_text = adv.get("recommendation", "")
            url = adv.get("url", "")
            cwe = _normalize_cwe(adv.get("cwe", ""))
            vuln_versions = adv.get("vulnerable_versions", "")
            patched_versions = adv.get("patched_versions", "")

            recommendation = recommendation_text or (
                f"Update {module_name} to {patched_versions}." if patched_versions else
                f"No automatic fix for {module_name}."
            )

            findings.append(ToolFinding(
                title=title,
                description=overview,
                severity=severity,
                type="dependency",
                file_path="package.json",
                line_start=0,
                line_end=0,
                code_snippet=f"{module_name}@{vuln_versions}",
                confidence="high",
                cwe_id=cwe,
                tool_name="npm_audit",
                recommendation=recommendation,
                metadata={
                    "advisory_id": adv_id,
                    "package": module_name,
                    "advisory_url": url,
                    "vulnerable_versions": vuln_versions,
                    "patched_versions": patched_versions,
                },
            ))
        logger.info("yarn audit found %d advisories", len(findings))
        return findings

    def _parse_output(self, raw_json: str) -> list[ToolFinding]:
        """Parse npm audit JSON output into ToolFinding objects.

        npm audit v7+ (npm 7+) has a different JSON format than v6.
        We support both formats.
        """
        findings: list[ToolFinding] = []

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse npm audit JSON: %s", e)
            return findings

        # npm 7+ format: { "vulnerabilities": { "pkg-name": { ... } } }
        vulnerabilities = data.get("vulnerabilities", {})
        if vulnerabilities:
            findings = self._parse_v7(vulnerabilities)
        else:
            # npm 6 format: { "advisories": { "id": { ... } } }
            advisories = data.get("advisories", {})
            if advisories:
                findings = self._parse_v6(advisories)

        logger.info("npm audit found %d vulnerabilities", len(findings))
        return findings

    def _parse_v7(self, vulnerabilities: dict) -> list[ToolFinding]:
        """Parse npm audit v7+ format."""
        findings: list[ToolFinding] = []

        for pkg_name, vuln_data in vulnerabilities.items():
            severity_raw = vuln_data.get("severity", "info").lower()
            severity = SEVERITY_MAP.get(severity_raw, "info")

            # vuln_data may have "via" which lists the actual advisories
            via_list = vuln_data.get("via", [])
            range_str = vuln_data.get("range", "")
            fix_available = vuln_data.get("fixAvailable")

            # Process each advisory in "via"
            if via_list and isinstance(via_list[0], dict):
                for advisory in via_list:
                    if not isinstance(advisory, dict):
                        continue

                    title = advisory.get("title", f"Vulnerability in {pkg_name}")
                    url = advisory.get("url", "")
                    adv_severity = advisory.get("severity", severity_raw).lower()
                    cwe_id = _normalize_cwe(advisory.get("cwe", []))

                    recommendation = ""
                    if fix_available:
                        if isinstance(fix_available, dict):
                            fix_name = fix_available.get("name", pkg_name)
                            fix_ver = fix_available.get("version", "latest")
                            recommendation = f"Update {fix_name} to version {fix_ver}."
                        else:
                            recommendation = f"Run 'npm audit fix' to resolve."
                    else:
                        recommendation = (
                            f"No automatic fix available for {pkg_name}. "
                            "Consider finding an alternative package."
                        )

                    findings.append(ToolFinding(
                        title=title,
                        description=f"Vulnerable versions: {range_str}",
                        severity=SEVERITY_MAP.get(adv_severity, severity),
                        type="dependency",
                        file_path="package.json",
                        line_start=0,
                        line_end=0,
                        code_snippet=f"{pkg_name}@{range_str}",
                        confidence="high",
                        cwe_id=cwe_id,
                        tool_name="npm_audit",
                        recommendation=recommendation,
                        metadata={
                            "package": pkg_name,
                            "advisory_url": url,
                            "range": range_str,
                        },
                    ))
            else:
                # "via" contains just package names (transitive deps)
                via_names = [v if isinstance(v, str) else v.get("name", "") for v in via_list]
                recommendation = ""
                if fix_available:
                    recommendation = "Run 'npm audit fix' to resolve."
                else:
                    recommendation = f"No automatic fix for {pkg_name}. Check transitive dependencies: {', '.join(via_names)}."

                findings.append(ToolFinding(
                    title=f"Vulnerability in {pkg_name}",
                    description=f"Affected via: {', '.join(via_names)}. Range: {range_str}",
                    severity=severity,
                    type="dependency",
                    file_path="package.json",
                    line_start=0,
                    line_end=0,
                    code_snippet=f"{pkg_name}@{range_str}",
                    confidence="medium",
                    cwe_id="",
                    tool_name="npm_audit",
                    recommendation=recommendation,
                    metadata={
                        "package": pkg_name,
                        "via": via_names,
                        "range": range_str,
                    },
                ))

        return findings

    def _parse_v6(self, advisories: dict) -> list[ToolFinding]:
        """Parse npm audit v6 format."""
        findings: list[ToolFinding] = []

        for adv_id, advisory in advisories.items():
            title = advisory.get("title", f"Advisory #{adv_id}")
            module_name = advisory.get("module_name", "")
            severity_raw = advisory.get("severity", "info").lower()
            severity = SEVERITY_MAP.get(severity_raw, "info")
            overview = advisory.get("overview", "")
            recommendation_text = advisory.get("recommendation", "")
            url = advisory.get("url", "")
            cwe = _normalize_cwe(advisory.get("cwe", ""))
            vulnerable_versions = advisory.get("vulnerable_versions", "")
            patched_versions = advisory.get("patched_versions", "")

            recommendation = recommendation_text
            if not recommendation and patched_versions:
                recommendation = f"Update {module_name} to {patched_versions}."

            findings.append(ToolFinding(
                title=title,
                description=overview,
                severity=severity,
                type="dependency",
                file_path="package.json",
                line_start=0,
                line_end=0,
                code_snippet=f"{module_name}@{vulnerable_versions}",
                confidence="high",
                cwe_id=cwe,
                tool_name="npm_audit",
                recommendation=recommendation,
                metadata={
                    "advisory_id": adv_id,
                    "package": module_name,
                    "advisory_url": url,
                    "vulnerable_versions": vulnerable_versions,
                    "patched_versions": patched_versions,
                },
            ))

        return findings

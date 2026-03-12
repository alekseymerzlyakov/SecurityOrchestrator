"""ESLint security plugin runner."""

import json
import logging
import os
import shutil

from backend.services.tool_runners.base import BaseToolRunner, ToolFinding

logger = logging.getLogger(__name__)

# ESLint severity: 1 = warning, 2 = error
SEVERITY_MAP = {
    2: "high",
    1: "medium",
}

# Security-focused rules to enable
SECURITY_RULES = {
    "security/detect-object-injection": "warn",
    "security/detect-non-literal-regexp": "warn",
    "security/detect-unsafe-regex": "warn",
    "security/detect-eval-with-expression": "error",
    "security/detect-no-csrf-before-method-override": "warn",
    "security/detect-possible-timing-attacks": "warn",
    "security/detect-pseudoRandomBytes": "warn",
    "security/detect-buffer-noassert": "warn",
    "security/detect-child-process": "warn",
    "security/detect-disable-mustache-escape": "warn",
    "security/detect-new-buffer": "warn",
    "security/detect-non-literal-fs-filename": "warn",
    "security/detect-non-literal-require": "warn",
    "no-unsanitized/method": "error",
    "no-unsanitized/property": "error",
}

# Map ESLint rule IDs to CWE
RULE_CWE_MAP = {
    "security/detect-eval-with-expression": "CWE-95",
    "security/detect-unsafe-regex": "CWE-1333",
    "security/detect-object-injection": "CWE-94",
    "security/detect-non-literal-regexp": "CWE-185",
    "security/detect-no-csrf-before-method-override": "CWE-352",
    "security/detect-possible-timing-attacks": "CWE-208",
    "security/detect-pseudoRandomBytes": "CWE-338",
    "security/detect-child-process": "CWE-78",
    "security/detect-non-literal-fs-filename": "CWE-22",
    "security/detect-non-literal-require": "CWE-95",
    "security/detect-new-buffer": "CWE-120",
    "no-unsanitized/method": "CWE-79",
    "no-unsanitized/property": "CWE-79",
}


class EslintRunner(BaseToolRunner):
    name = "eslint_security"
    binary_name = "eslint"

    @staticmethod
    def _find_eslint() -> tuple[str, str | None]:
        """Return (eslint_binary, node_path_for_global_plugins).

        ESLint 10 (flat config) dropped --no-eslintrc; we use --no-config-lookup.
        Plugins must be resolvable — look for them next to the eslint binary first,
        then fall back to npx with the repo's local node_modules.
        """
        # Try the global eslint binary (installed via npm -g)
        eslint_bin = shutil.which("eslint")
        if eslint_bin:
            # Global node_modules are usually two levels up from bin/eslint
            # e.g. ~/.nvm/versions/node/vX.Y.Z/bin/eslint
            #   -> ~/.nvm/versions/node/vX.Y.Z/lib/node_modules
            bin_dir = os.path.dirname(eslint_bin)
            node_root = os.path.dirname(bin_dir)  # e.g. .../node/vX.Y.Z
            global_modules = os.path.join(node_root, "lib", "node_modules")
            if os.path.isdir(os.path.join(global_modules, "eslint-plugin-security")):
                return eslint_bin, global_modules
        # Fall back to npx (will use local node_modules if available)
        return "npx eslint".split()[0], None

    async def run(self, repo_path: str, config: dict = None, on_progress=None) -> list[ToolFinding]:
        config = config or {}

        # Build scan target: prefer packages/ subdirectory if it exists
        scan_target = repo_path
        packages_dir = os.path.join(repo_path, "packages")
        if os.path.isdir(packages_dir):
            scan_target = packages_dir

        # Build rules JSON for the command
        rules = config.get("rules", SECURITY_RULES)
        rules_json = json.dumps(rules)

        eslint_bin, node_path = self._find_eslint()

        env = os.environ.copy()
        if node_path:
            existing = env.get("NODE_PATH", "")
            env["NODE_PATH"] = f"{node_path}:{existing}" if existing else node_path

        if on_progress:
            await on_progress("Starting ESLint security scan...", 0)

        # ESLint 10 flat config: --no-config-lookup replaces --no-eslintrc
        cmd = [
            eslint_bin,
            "--no-config-lookup",
            "--plugin", "security",
            "--plugin", "no-unsanitized",
            "--rule", rules_json,
            "--format", "json",
            scan_target,
        ]

        # ESLint outputs the full JSON at the end (not streaming per file),
        # but we can show a heartbeat message so UI doesn't look frozen.
        # Count JS/TS files first for a quick estimate.
        if on_progress:
            try:
                js_files = sum(
                    1 for root, _, files in os.walk(scan_target)
                    for f in files
                    if f.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"))
                    and "node_modules" not in root
                )
                await on_progress(f"Scanning {js_files} JS/TS files for security issues...", 0)
            except Exception:
                pass

        stdout, stderr, rc = await self._run_command(cmd, cwd=repo_path, env=env)

        # Fall back to legacy --no-eslintrc flag for ESLint 8
        if rc not in (0, 1) and ("no-config-lookup" in (stderr or "") or "Invalid option" in (stderr or "")):
            cmd_legacy = [
                eslint_bin,
                "--no-eslintrc",
                "--plugin", "security",
                "--plugin", "no-unsanitized",
                "--rule", rules_json,
                "--format", "json",
                "--ext", ".js,.jsx,.ts,.tsx,.mjs,.cjs",
                scan_target,
            ]
            stdout, stderr, rc = await self._run_command(cmd_legacy, cwd=repo_path, env=env)

        # ESLint returns 1 when there are linting errors, which is expected
        if rc not in (0, 1) and not stdout:
            logger.error("ESLint failed (rc=%d): %s", rc, stderr)
            return []

        if not stdout:
            logger.info("ESLint security: no issues found")
            if on_progress:
                await on_progress("No security issues found", 0)
            return []

        findings = self._parse_output(stdout, repo_path)
        if on_progress:
            await on_progress(f"Done — {len(findings)} security issues found", len(findings))
        return findings

    def _parse_output(self, raw_json: str, repo_path: str) -> list[ToolFinding]:
        """Parse ESLint JSON output into ToolFinding objects."""
        findings: list[ToolFinding] = []

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse ESLint JSON: %s", e)
            return findings

        if not isinstance(data, list):
            logger.warning("Unexpected ESLint output format")
            return findings

        for file_result in data:
            file_path = file_result.get("filePath", "")
            if file_path.startswith(repo_path):
                file_path = os.path.relpath(file_path, repo_path)

            messages = file_result.get("messages", [])
            source_lines = file_result.get("source", "").split("\n") if file_result.get("source") else []

            for msg in messages:
                rule_id = msg.get("ruleId", "")
                if not rule_id:
                    continue

                # Only include messages from security-related rules
                is_security = (
                    rule_id.startswith("security/")
                    or rule_id.startswith("no-unsanitized/")
                )
                if not is_security:
                    continue

                severity_num = msg.get("severity", 1)
                severity = SEVERITY_MAP.get(severity_num, "medium")
                message = msg.get("message", "")
                line_start = msg.get("line", 0)
                line_end = msg.get("endLine", line_start)
                column = msg.get("column", 0)

                # Extract code snippet
                code_snippet = ""
                if source_lines and 0 < line_start <= len(source_lines):
                    # Get a few lines of context
                    start_idx = max(0, line_start - 2)
                    end_idx = min(len(source_lines), line_end + 1)
                    code_snippet = "\n".join(source_lines[start_idx:end_idx])

                cwe_id = RULE_CWE_MAP.get(rule_id, "")

                findings.append(ToolFinding(
                    title=f"ESLint: {rule_id}",
                    description=message,
                    severity=severity,
                    type=self._infer_type(rule_id),
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_end,
                    code_snippet=code_snippet,
                    confidence="medium",
                    cwe_id=cwe_id,
                    tool_name="eslint_security",
                    recommendation=self._get_recommendation(rule_id),
                    metadata={
                        "rule_id": rule_id,
                        "column": column,
                    },
                ))

        logger.info("ESLint security found %d issues", len(findings))
        return findings

    @staticmethod
    def _infer_type(rule_id: str) -> str:
        """Infer finding type from ESLint rule ID."""
        if "unsanitized" in rule_id or "xss" in rule_id:
            return "xss"
        if "eval" in rule_id or "require" in rule_id:
            return "injection"
        if "csrf" in rule_id:
            return "csrf"
        if "regex" in rule_id or "regexp" in rule_id:
            return "dos"
        if "child-process" in rule_id:
            return "injection"
        if "fs-filename" in rule_id or "path" in rule_id:
            return "path_traversal"
        if "timing" in rule_id:
            return "crypto"
        if "random" in rule_id:
            return "crypto"
        return "code_quality"

    @staticmethod
    def _get_recommendation(rule_id: str) -> str:
        """Provide a recommendation based on the rule."""
        recommendations = {
            "security/detect-eval-with-expression": (
                "Avoid using eval() with dynamic expressions. "
                "Use safer alternatives like JSON.parse() or a sandboxed interpreter."
            ),
            "security/detect-unsafe-regex": (
                "This regex may be vulnerable to ReDoS (Regular Expression Denial of Service). "
                "Simplify the pattern or use a safe-regex library."
            ),
            "security/detect-object-injection": (
                "Using user-controlled keys to access objects can lead to prototype pollution. "
                "Validate or whitelist the keys before use."
            ),
            "security/detect-non-literal-regexp": (
                "Constructing regexes from dynamic input can lead to ReDoS. "
                "Sanitize user input before using it in RegExp."
            ),
            "security/detect-child-process": (
                "Spawning child processes with user input can lead to command injection. "
                "Validate and sanitize all inputs."
            ),
            "security/detect-non-literal-fs-filename": (
                "Using dynamic file paths can lead to path traversal attacks. "
                "Validate and sanitize file paths, use path.resolve() with a base directory."
            ),
            "no-unsanitized/method": (
                "Passing unsanitized data to DOM manipulation methods can lead to XSS. "
                "Use textContent instead of innerHTML, or sanitize with DOMPurify."
            ),
            "no-unsanitized/property": (
                "Setting unsanitized data to DOM properties can lead to XSS. "
                "Use textContent instead of innerHTML, or sanitize with DOMPurify."
            ),
        }
        return recommendations.get(rule_id, "Review and fix the flagged code pattern.")

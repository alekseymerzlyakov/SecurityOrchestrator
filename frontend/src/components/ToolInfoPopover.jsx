import { useState, useRef, useEffect } from 'react';
import { InformationCircleIcon, XMarkIcon } from '@heroicons/react/24/outline';

/**
 * Detailed info about each security tool.
 */
const TOOL_INFO = {
  semgrep: {
    displayName: 'Semgrep',
    category: 'SAST',
    description:
      'Lightweight static analysis tool that uses pattern-matching to find bugs, security vulnerabilities, and enforce code standards. Supports 30+ languages with community and pro rulesets.',
    detects: [
      'XSS (Cross-Site Scripting)',
      'SQL/NoSQL injection patterns',
      'Insecure deserialization',
      'Prototype pollution',
      'Hard-coded secrets in code',
      'Insecure use of crypto',
      'Path traversal',
      'Open redirect',
    ],
    strengths: [
      'Very fast — pattern-based, no compilation needed',
      'Low false-positive rate with curated rules',
      '2,000+ community rules + auto config',
      'Understands code structure (AST), not just regex',
    ],
    limitations: [
      'Cannot follow data flow across files (no taint analysis in OSS)',
      'May miss deeply nested logic vulnerabilities',
      'Rule quality depends on ruleset selected',
    ],
    outputFormat: 'JSON / SARIF',
    url: 'https://semgrep.dev',
    install: 'pip install semgrep',
  },
  gitleaks: {
    displayName: 'Gitleaks',
    category: 'Secret Scanner',
    description:
      'Scans the entire Git history for hard-coded secrets, API keys, tokens, and credentials. Catches secrets that were committed even if later removed.',
    detects: [
      'AWS access keys / secret keys',
      'API tokens (GitHub, Slack, Stripe, etc.)',
      'Private keys (SSH, PGP, RSA)',
      'Database connection strings',
      'OAuth client secrets',
      'JWT signing keys',
      'Generic high-entropy strings',
    ],
    strengths: [
      'Scans full Git history, not just current files',
      'Catches secrets that were "deleted" but remain in commits',
      '150+ built-in rules for known secret formats',
      'Very fast — written in Go',
    ],
    limitations: [
      'May flag test/mock secrets as real findings',
      'Entropy-based detection can produce false positives',
      'Does not scan binary files',
    ],
    outputFormat: 'JSON / CSV / SARIF',
    url: 'https://gitleaks.io',
    install: 'brew install gitleaks',
  },
  trivy: {
    displayName: 'Trivy',
    category: 'Dependency Scanner',
    description:
      'Comprehensive vulnerability scanner for dependencies (SCA). Scans package lock files (yarn.lock, package-lock.json) against the NVD and other vulnerability databases.',
    detects: [
      'Known CVEs in npm/yarn packages',
      'Vulnerable transitive dependencies',
      'Outdated packages with known exploits',
      'License compliance issues',
      'Misconfigurations in IaC files',
    ],
    strengths: [
      'Huge vulnerability database (NVD, GitHub Advisory, etc.)',
      'Scans lock files for precise version matching',
      'Very low false-positive rate — matches exact CVEs',
      'Also supports Docker images, Kubernetes, Terraform',
    ],
    limitations: [
      'Only finds KNOWN vulnerabilities (CVE-based)',
      'Cannot detect zero-day or custom vulnerabilities',
      'Requires DB download on first run (~30 MB)',
    ],
    outputFormat: 'JSON / Table / SARIF / CycloneDX',
    url: 'https://trivy.dev',
    install: 'brew install trivy',
  },
  npm_audit: {
    displayName: 'npm audit',
    category: 'Dependency Scanner',
    description:
      'Built-in npm tool that checks installed packages against the npm advisory database for known vulnerabilities. Works with package-lock.json.',
    detects: [
      'Known vulnerabilities in direct dependencies',
      'Vulnerable transitive (nested) dependencies',
      'Packages with published security advisories',
    ],
    strengths: [
      'Zero installation needed — built into npm',
      'Direct integration with npm advisory database',
      'Suggests fix commands (npm audit fix)',
      'Fast and lightweight',
    ],
    limitations: [
      'Only works with npm (not yarn-only projects)',
      'Advisory database may lag behind NVD',
      'Cannot fix breaking version changes automatically',
      'No scanning of code — dependencies only',
    ],
    outputFormat: 'JSON / Human-readable',
    url: 'https://docs.npmjs.com/cli/audit',
    install: 'Built-in with npm',
  },
  eslint_security: {
    displayName: 'ESLint Security',
    category: 'SAST (JS-specific)',
    description:
      'ESLint with security-focused plugins (eslint-plugin-security, eslint-plugin-no-unsanitized). Finds JavaScript/TypeScript-specific security anti-patterns.',
    detects: [
      'eval() with dynamic expressions',
      'innerHTML / dangerouslySetInnerHTML misuse',
      'Unsafe regex (ReDoS)',
      'Object injection via bracket notation',
      'Child process spawning with user input',
      'Non-literal require() calls',
      'CSRF issues (method override)',
      'Timing attack patterns',
    ],
    strengths: [
      'Deep understanding of JS/TS syntax and semantics',
      'Rules map directly to CWE IDs',
      'Integrates with existing ESLint workflows',
      'Catches JS-specific patterns Semgrep may miss',
    ],
    limitations: [
      'JavaScript/TypeScript only',
      'detect-object-injection rule has high false positive rate',
      'Requires ESLint plugins installed globally',
      'No cross-file analysis',
    ],
    outputFormat: 'JSON',
    url: 'https://github.com/eslint-community/eslint-plugin-security',
    install: 'npm install -g eslint eslint-plugin-security eslint-plugin-no-unsanitized',
  },
  retirejs: {
    displayName: 'Retire.js',
    category: 'Dependency Scanner',
    description:
      'Detects the use of JavaScript libraries with known vulnerabilities. Scans source files for embedded/bundled libraries (not just package.json).',
    detects: [
      'Vulnerable embedded JS libraries (jQuery, Angular, etc.)',
      'Outdated bundled frameworks',
      'Known CVEs in client-side libraries',
    ],
    strengths: [
      'Can find libraries embedded directly in source code',
      'Detects bundled/vendored libraries others miss',
      'Complements npm audit / Trivy for client-side libs',
    ],
    limitations: [
      'Smaller vulnerability database than Trivy',
      'May not detect custom-built or minified libraries',
      'Slow on large node_modules directories',
    ],
    outputFormat: 'JSON / Text / CycloneDX',
    url: 'https://retirejs.github.io/retire.js/',
    install: 'npm install -g retire',
  },
  ai_analysis: {
    displayName: 'AI Deep Analysis',
    category: 'AI-Powered',
    description:
      'Uses LLM (Claude, GPT-4, Gemini, or local models) to perform deep semantic code analysis. Understands business logic, data flows across files, and architectural security issues that static tools cannot detect.',
    detects: [
      'Business logic vulnerabilities',
      'Complex authentication/authorization flaws',
      'Cross-file data flow issues',
      'Architectural security weaknesses',
      'Context-dependent vulnerabilities',
      'Insecure design patterns',
      'Missing security controls',
      'Race conditions and concurrency issues',
    ],
    strengths: [
      'Understands code semantics and intent',
      'Analyzes cross-file data flows',
      'Catches logic errors tools cannot find',
      'Provides detailed explanations and fix suggestions',
      'Adapts to project-specific context',
    ],
    limitations: [
      'Costs money per token (API calls)',
      'Cannot analyze entire large repos at once',
      'May produce false positives on unfamiliar patterns',
      'Speed depends on model and API latency',
      'Quality varies by model (Opus > Sonnet > Haiku)',
    ],
    outputFormat: 'Structured JSON findings',
    url: null,
    install: 'Configure API key in Settings → AI Providers',
  },
};

/**
 * Fallback for tools not in the dictionary.
 */
const DEFAULT_INFO = {
  displayName: 'Unknown Tool',
  category: 'Security Tool',
  description: 'No detailed information available for this tool.',
  detects: [],
  strengths: [],
  limitations: [],
  outputFormat: 'N/A',
  url: null,
  install: 'N/A',
};


export default function ToolInfoPopover({ toolName }) {
  const [open, setOpen] = useState(false);
  const popoverRef = useRef(null);
  const btnRef = useRef(null);

  const info = TOOL_INFO[toolName] || { ...DEFAULT_INFO, displayName: toolName };

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (
        popoverRef.current && !popoverRef.current.contains(e.target) &&
        btnRef.current && !btnRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    function handleKey(e) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open]);

  return (
    <span className="relative inline-flex items-center">
      <button
        ref={btnRef}
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        className="ml-1 text-gray-400 hover:text-blue-500 transition-colors focus:outline-none"
        title={`Info about ${info.displayName}`}
      >
        <InformationCircleIcon className="h-4 w-4" />
      </button>

      {open && (
        <div
          ref={popoverRef}
          className="absolute z-50 left-6 top-0 w-[420px] bg-white rounded-xl shadow-2xl border border-gray-200 overflow-hidden animate-in"
          style={{ maxHeight: '520px' }}
        >
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-5 py-3 flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-base">{info.displayName}</h3>
              <span className="text-blue-200 text-xs font-medium">{info.category}</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-white/70 hover:text-white">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Body — scrollable */}
          <div className="px-5 py-4 overflow-y-auto text-sm" style={{ maxHeight: '430px' }}>
            {/* Description */}
            <p className="text-gray-700 leading-relaxed mb-4">{info.description}</p>

            {/* Detects */}
            {info.detects.length > 0 && (
              <div className="mb-4">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                  🔍 What it detects
                </h4>
                <ul className="space-y-0.5">
                  {info.detects.map((d, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-gray-600">
                      <span className="text-blue-400 mt-0.5 shrink-0">•</span>
                      <span>{d}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Strengths */}
            {info.strengths.length > 0 && (
              <div className="mb-4">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                  ✅ Strengths
                </h4>
                <ul className="space-y-0.5">
                  {info.strengths.map((s, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-gray-600">
                      <span className="text-green-500 mt-0.5 shrink-0">+</span>
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Limitations */}
            {info.limitations.length > 0 && (
              <div className="mb-4">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                  ⚠️ Limitations
                </h4>
                <ul className="space-y-0.5">
                  {info.limitations.map((l, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-gray-600">
                      <span className="text-amber-500 mt-0.5 shrink-0">−</span>
                      <span>{l}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Footer meta */}
            <div className="border-t border-gray-100 pt-3 mt-3 space-y-1.5 text-xs text-gray-500">
              <div className="flex gap-2">
                <span className="font-medium text-gray-600 w-20 shrink-0">Output:</span>
                <span className="font-mono">{info.outputFormat}</span>
              </div>
              <div className="flex gap-2">
                <span className="font-medium text-gray-600 w-20 shrink-0">Install:</span>
                <span className="font-mono bg-gray-50 px-1.5 py-0.5 rounded">{info.install}</span>
              </div>
              {info.url && (
                <div className="flex gap-2">
                  <span className="font-medium text-gray-600 w-20 shrink-0">Website:</span>
                  <a
                    href={info.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    {info.url}
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </span>
  );
}

export { TOOL_INFO };

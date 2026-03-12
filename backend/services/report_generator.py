"""Report generation service.

Generates security scan reports in JSON, HTML, and PDF formats.
Supports executive (high-level summary) and technical (detailed) report types.
"""

import json
import logging
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from backend.config import REPORTS_DIR
from backend.database import async_session
from backend.models.scan import Scan, ScanStep, Finding
from backend.models.project import Project

logger = logging.getLogger(__name__)

# Ensure reports directory exists
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_report(
    scan_id: int,
    format: str = "html",
    report_type: str = "technical",
) -> str:
    """Generate a report for a completed scan.

    Args:
        scan_id: The scan ID.
        format: Output format — "json", "html", or "pdf".
        report_type: "executive" (summary) or "technical" (detailed).

    Returns:
        Absolute file path to the generated report.
    """
    # Load data
    report_data = await _load_report_data(scan_id)

    if not report_data:
        raise ValueError(f"Scan {scan_id} not found or has no data")

    # Build filename
    ext = format if format != "pdf" else "pdf"
    filename = f"scan_{scan_id}_{report_type}.{ext}"
    file_path = str(REPORTS_DIR / filename)

    if format == "json":
        _generate_json(report_data, file_path, report_type)
    elif format == "html":
        _generate_html(report_data, file_path, report_type)
    elif format == "pdf":
        _generate_pdf(report_data, file_path, report_type)
    else:
        raise ValueError(f"Unsupported format: {format}")

    logger.info("Report generated: %s", file_path)
    return file_path


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

async def _load_report_data(scan_id: int) -> dict | None:
    """Load all data needed for the report from the database."""
    from backend.models.settings import AIModel, AIProvider
    from backend.models.scan import TokenUsage

    async with async_session() as session:
        # Load scan
        result = await session.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalars().first()
        if not scan:
            return None

        # Load project
        proj_result = await session.execute(
            select(Project).where(Project.id == scan.project_id)
        )
        project = proj_result.scalars().first()

        # Load steps
        steps_result = await session.execute(
            select(ScanStep)
            .where(ScanStep.scan_id == scan_id)
            .order_by(ScanStep.step_order)
        )
        steps = steps_result.scalars().all()

        # Load findings
        findings_result = await session.execute(
            select(Finding)
            .where(Finding.scan_id == scan_id)
            .order_by(Finding.severity, Finding.id)
        )
        findings = findings_result.scalars().all()

        # Load token usage records
        token_result = await session.execute(
            select(TokenUsage).where(TokenUsage.scan_id == scan_id).order_by(TokenUsage.timestamp)
        )
        token_records = token_result.scalars().all()

        # Load all configured AI models for the cost forecast table
        models_result = await session.execute(select(AIModel))
        all_models = models_result.scalars().all()

        providers_result = await session.execute(select(AIProvider))
        providers = {p.id: p.name for p in providers_result.scalars().all()}

    # Compute summary statistics
    severity_counts = Counter(f.severity for f in findings)
    type_counts = Counter(f.type for f in findings)
    tool_counts = Counter(f.tool_name for f in findings)

    # Build token usage breakdown
    token_breakdown = []
    for t in token_records:
        token_breakdown.append({
            "chunk": t.chunk_description or "unknown",
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
            "cost_usd": round(t.cost_usd, 6),
        })

    # Build AI cost forecast: for each model, estimate cost for a full AI scan
    cost_forecast = []
    if project:
        try:
            from backend.services.token_tracker import estimate_scan_cost as _estimate
            # Use a lightweight estimate — reuse chunking module
            base_estimate = await _estimate(
                repo_path=project.repo_path,
                model={
                    "input_price_per_mtok": 1.0,
                    "output_price_per_mtok": 5.0,
                    "context_window": 200000,
                    "max_tokens_per_run": 1_000_000,
                    "max_budget_usd": 100,
                },
            )
            inp_tok = base_estimate["estimated_input_tokens"]
            out_tok = base_estimate["estimated_output_tokens"]

            for m in all_models:
                inp_p = m.input_price_per_mtok or 0.0
                out_p = m.output_price_per_mtok or 0.0
                cost = round((inp_tok / 1_000_000) * inp_p + (out_tok / 1_000_000) * out_p, 4)
                cost_forecast.append({
                    "model_name": m.name,
                    "model_id": m.model_id,
                    "provider": providers.get(m.provider_id, "unknown"),
                    "total_files": base_estimate["total_files"],
                    "total_code_tokens": base_estimate["total_code_tokens"],
                    "estimated_chunks": base_estimate["estimated_chunks"],
                    "estimated_input_tokens": inp_tok,
                    "estimated_output_tokens": out_tok,
                    "input_price_per_mtok": inp_p,
                    "output_price_per_mtok": out_p,
                    "estimated_total_cost_usd": cost,
                    "max_budget_usd": m.max_budget_usd or 50.0,
                    "within_budget": cost <= (m.max_budget_usd or 50.0),
                })
            cost_forecast.sort(key=lambda x: x["estimated_total_cost_usd"])
        except Exception as exc:
            logger.warning("Could not build cost forecast: %s", exc)

    return {
        "scan": {
            "id": scan.id,
            "status": scan.status,
            "mode": scan.mode,
            "branch": scan.branch,
            "started_at": scan.started_at.isoformat() if scan.started_at else None,
            "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
            "total_files": scan.total_files,
            "files_processed": scan.files_processed,
            "tokens_used": scan.tokens_used,
            "cost_usd": scan.cost_usd,
        },
        "project": {
            "id": project.id if project else None,
            "name": project.name if project else "Unknown",
            "repo_path": project.repo_path if project else "",
        },
        "steps": [
            {
                "tool_name": s.tool_name,
                "status": s.status,
                "findings_count": s.findings_count,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "error_message": s.error_message,
            }
            for s in steps
        ],
        "findings": [
            {
                "id": f.id,
                "type": f.type,
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "file_path": f.file_path,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "code_snippet": f.code_snippet,
                "tool_name": f.tool_name,
                "confidence": f.confidence,
                "cwe_id": f.cwe_id,
                "recommendation": f.recommendation,
                "status": f.status,
            }
            for f in findings
        ],
        "summary": {
            "total_findings": len(findings),
            "severity_counts": dict(severity_counts),
            "type_counts": dict(type_counts),
            "tool_counts": dict(tool_counts),
            "critical_count": severity_counts.get("critical", 0),
            "high_count": severity_counts.get("high", 0),
            "medium_count": severity_counts.get("medium", 0),
            "low_count": severity_counts.get("low", 0),
            "info_count": severity_counts.get("info", 0),
        },
        "token_breakdown": token_breakdown,
        "cost_forecast": cost_forecast,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def _generate_json(data: dict, file_path: str, report_type: str):
    """Generate a JSON report."""
    if report_type == "executive":
        # Executive: only summary, no detailed findings
        output = {
            "report_type": "executive",
            "generated_at": data["generated_at"],
            "project": data["project"],
            "scan": data["scan"],
            "summary": data["summary"],
            "steps": data["steps"],
        }
    else:
        # Technical: full data
        output = {
            "report_type": "technical",
            **data,
        }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

# Severity ordering for sorting
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SEVERITY_COLORS = {
    "critical": "#dc2626",
    "high": "#ea580c",
    "medium": "#ca8a04",
    "low": "#2563eb",
    "info": "#6b7280",
}


def _generate_html(data: dict, file_path: str, report_type: str):
    """Generate an HTML report using an inline Jinja2-style template."""
    try:
        from jinja2 import Template
    except ImportError:
        # Fallback: generate simple HTML without Jinja2
        _generate_html_fallback(data, file_path, report_type)
        return

    template = Template(HTML_TEMPLATE)
    html = template.render(
        data=data,
        report_type=report_type,
        severity_colors=SEVERITY_COLORS,
        severity_order=SEVERITY_ORDER,
        generated_at=data["generated_at"],
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)


def _generate_html_fallback(data: dict, file_path: str, report_type: str):
    """Minimal HTML report without Jinja2."""
    summary = data["summary"]
    project = data["project"]
    scan = data["scan"]

    findings_html = ""
    if report_type == "technical":
        for f in data["findings"]:
            sev = f.get("severity", "info")
            color = SEVERITY_COLORS.get(sev, "#6b7280")
            findings_html += f"""
            <tr>
                <td><span style="color:{color};font-weight:bold">{sev.upper()}</span></td>
                <td>{_escape_html(f.get('title', ''))}</td>
                <td>{_escape_html(f.get('file_path', ''))}</td>
                <td>{f.get('line_start', '')}</td>
                <td>{_escape_html(f.get('tool_name', ''))}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Security Report - {_escape_html(project['name'])}</title>
    <style>{CSS_STYLES}</style>
</head>
<body>
    <div class="container">
        <h1>Security Scan Report</h1>
        <p><strong>Project:</strong> {_escape_html(project['name'])}</p>
        <p><strong>Branch:</strong> {_escape_html(scan.get('branch', ''))}</p>
        <p><strong>Scan ID:</strong> {scan['id']}</p>
        <p><strong>Generated:</strong> {data['generated_at']}</p>
        <p><strong>Report Type:</strong> {report_type.title()}</p>

        <h2>Summary</h2>
        <div class="summary-grid">
            <div class="summary-card critical">
                <div class="count">{summary['critical_count']}</div>
                <div class="label">Critical</div>
            </div>
            <div class="summary-card high">
                <div class="count">{summary['high_count']}</div>
                <div class="label">High</div>
            </div>
            <div class="summary-card medium">
                <div class="count">{summary['medium_count']}</div>
                <div class="label">Medium</div>
            </div>
            <div class="summary-card low">
                <div class="count">{summary['low_count']}</div>
                <div class="label">Low</div>
            </div>
            <div class="summary-card info">
                <div class="count">{summary['info_count']}</div>
                <div class="label">Info</div>
            </div>
        </div>

        {"<h2>Findings</h2><table><thead><tr><th>Severity</th><th>Title</th><th>File</th><th>Line</th><th>Tool</th></tr></thead><tbody>" + findings_html + "</tbody></table>" if report_type == "technical" else ""}
    </div>
</body>
</html>"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

def _generate_pdf(data: dict, file_path: str, report_type: str):
    """Generate a PDF report by rendering HTML and converting with WeasyPrint."""
    # First generate HTML to a temp path
    html_path = file_path.replace(".pdf", "_temp.html")
    _generate_html(data, html_path, report_type)

    try:
        from weasyprint import HTML
        HTML(filename=html_path).write_pdf(file_path)
        logger.info("PDF report generated via WeasyPrint: %s", file_path)
    except ImportError:
        logger.warning(
            "WeasyPrint not installed — falling back to HTML report. "
            "Install with: pip install weasyprint"
        )
        # Just copy the HTML as the output
        import shutil
        final_html_path = file_path.replace(".pdf", ".html")
        shutil.move(html_path, final_html_path)
        raise RuntimeError(
            f"WeasyPrint not installed. HTML report saved to: {final_html_path}"
        )
    finally:
        # Clean up temp HTML
        if os.path.exists(html_path):
            os.remove(html_path)


# ---------------------------------------------------------------------------
# HTML escaping helper
# ---------------------------------------------------------------------------

def _escape_html(text: str) -> str:
    """Basic HTML escaping."""
    if not text:
        return ""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


# ---------------------------------------------------------------------------
# CSS Styles (shared between Jinja2 and fallback)
# ---------------------------------------------------------------------------

CSS_STYLES = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
        background: #f8fafc;
        color: #1e293b;
        line-height: 1.6;
    }
    .container {
        max-width: 1100px;
        margin: 0 auto;
        padding: 40px 24px;
    }
    h1 {
        font-size: 28px;
        margin-bottom: 8px;
        color: #0f172a;
        border-bottom: 3px solid #3b82f6;
        padding-bottom: 12px;
    }
    h2 {
        font-size: 20px;
        margin-top: 32px;
        margin-bottom: 16px;
        color: #1e293b;
    }
    h3 {
        font-size: 16px;
        margin-top: 20px;
        margin-bottom: 8px;
        color: #334155;
    }
    p { margin-bottom: 6px; }
    .summary-grid {
        display: flex;
        gap: 16px;
        margin: 20px 0;
        flex-wrap: wrap;
    }
    .summary-card {
        flex: 1;
        min-width: 120px;
        padding: 20px;
        border-radius: 8px;
        text-align: center;
        color: white;
    }
    .summary-card .count { font-size: 36px; font-weight: bold; }
    .summary-card .label { font-size: 14px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9; }
    .summary-card.critical { background: #dc2626; }
    .summary-card.high { background: #ea580c; }
    .summary-card.medium { background: #ca8a04; }
    .summary-card.low { background: #2563eb; }
    .summary-card.info { background: #6b7280; }
    table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 12px;
        font-size: 14px;
    }
    th, td {
        padding: 10px 12px;
        text-align: left;
        border-bottom: 1px solid #e2e8f0;
    }
    th {
        background: #f1f5f9;
        font-weight: 600;
        color: #475569;
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    tr:hover { background: #f8fafc; }
    .finding-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .finding-card .severity-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 4px;
        color: white;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
    }
    .finding-card .meta { color: #64748b; font-size: 13px; margin: 8px 0; }
    .finding-card pre {
        background: #1e293b;
        color: #e2e8f0;
        padding: 12px;
        border-radius: 6px;
        overflow-x: auto;
        font-size: 13px;
        margin: 10px 0;
    }
    .finding-card .recommendation {
        background: #f0fdf4;
        border-left: 4px solid #22c55e;
        padding: 10px 14px;
        margin-top: 10px;
        font-size: 14px;
    }
    .steps-table td.status-completed { color: #16a34a; }
    .steps-table td.status-failed { color: #dc2626; }
    .steps-table td.status-skipped { color: #9ca3af; }
    tfoot tr td { border-top: 2px solid #cbd5e1; }
    th small { font-weight:400; font-size:11px; display:block; }
    .footer {
        margin-top: 40px;
        padding-top: 20px;
        border-top: 1px solid #e2e8f0;
        color: #94a3b8;
        font-size: 13px;
        text-align: center;
    }
"""


# ---------------------------------------------------------------------------
# Jinja2 HTML Template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Security Report — {{ data.project.name }}</title>
    <style>""" + CSS_STYLES + """</style>
</head>
<body>
<div class="container">

    <h1>Security Scan Report</h1>
    <p><strong>Project:</strong> {{ data.project.name }}</p>
    <p><strong>Branch:</strong> {{ data.scan.branch }}</p>
    <p><strong>Scan ID:</strong> {{ data.scan.id }}</p>
    <p><strong>Status:</strong> {{ data.scan.status }}</p>
    <p><strong>Mode:</strong> {{ data.scan.mode }}</p>
    {% if data.scan.started_at %}
    <p><strong>Started:</strong> {{ data.scan.started_at }}</p>
    {% endif %}
    {% if data.scan.finished_at %}
    <p><strong>Finished:</strong> {{ data.scan.finished_at }}</p>
    {% endif %}
    <p><strong>Report Type:</strong> {{ report_type|title }}</p>
    <p><strong>Generated:</strong> {{ generated_at }}</p>

    <!-- ============ SUMMARY ============ -->
    <h2>Summary</h2>
    <div class="summary-grid">
        <div class="summary-card critical">
            <div class="count">{{ data.summary.critical_count }}</div>
            <div class="label">Critical</div>
        </div>
        <div class="summary-card high">
            <div class="count">{{ data.summary.high_count }}</div>
            <div class="label">High</div>
        </div>
        <div class="summary-card medium">
            <div class="count">{{ data.summary.medium_count }}</div>
            <div class="label">Medium</div>
        </div>
        <div class="summary-card low">
            <div class="count">{{ data.summary.low_count }}</div>
            <div class="label">Low</div>
        </div>
        <div class="summary-card info">
            <div class="count">{{ data.summary.info_count }}</div>
            <div class="label">Info</div>
        </div>
    </div>
    <p><strong>Total findings:</strong> {{ data.summary.total_findings }}</p>

    {% if data.scan.tokens_used %}
    <p><strong>Tokens used:</strong> {{ data.scan.tokens_used }}</p>
    {% endif %}
    {% if data.scan.cost_usd %}
    <p><strong>Estimated cost:</strong> ${{ "%.4f"|format(data.scan.cost_usd) }}</p>
    {% endif %}

    <!-- ============ SCAN STEPS ============ -->
    <h2>Scan Steps</h2>
    <table class="steps-table">
        <thead>
            <tr>
                <th>#</th>
                <th>Tool</th>
                <th>Status</th>
                <th>Findings</th>
                <th>Error</th>
            </tr>
        </thead>
        <tbody>
        {% for step in data.steps %}
            <tr>
                <td>{{ loop.index }}</td>
                <td>{{ step.tool_name }}</td>
                <td class="status-{{ step.status }}">{{ step.status }}</td>
                <td>{{ step.findings_count }}</td>
                <td>{{ step.error_message or '' }}</td>
            </tr>
        {% endfor %}
        </tbody>
    </table>

    {% if report_type == 'executive' %}
    <!-- ============ EXECUTIVE: BY-TYPE BREAKDOWN ============ -->
    <h2>Findings by Type</h2>
    <table>
        <thead><tr><th>Type</th><th>Count</th></tr></thead>
        <tbody>
        {% for type_name, count in data.summary.type_counts.items() %}
            <tr><td>{{ type_name }}</td><td>{{ count }}</td></tr>
        {% endfor %}
        </tbody>
    </table>

    <h2>Findings by Tool</h2>
    <table>
        <thead><tr><th>Tool</th><th>Count</th></tr></thead>
        <tbody>
        {% for tool_name, count in data.summary.tool_counts.items() %}
            <tr><td>{{ tool_name }}</td><td>{{ count }}</td></tr>
        {% endfor %}
        </tbody>
    </table>

    {% else %}
    <!-- ============ TECHNICAL: DETAILED FINDINGS ============ -->
    <h2>Detailed Findings</h2>

    {% for finding in data.findings %}
    <div class="finding-card">
        <span class="severity-badge" style="background:{{ severity_colors.get(finding.severity, '#6b7280') }}">
            {{ finding.severity|upper }}
        </span>
        <strong style="margin-left:8px">{{ finding.title }}</strong>
        <div class="meta">
            {% if finding.file_path %}
            <strong>File:</strong> {{ finding.file_path }}
            {% if finding.line_start %} (line {{ finding.line_start }}{% if finding.line_end and finding.line_end != finding.line_start %}-{{ finding.line_end }}{% endif %}){% endif %}
            &nbsp;|&nbsp;
            {% endif %}
            {% if finding.tool_name %}<strong>Tool:</strong> {{ finding.tool_name }} &nbsp;|&nbsp;{% endif %}
            {% if finding.confidence %}<strong>Confidence:</strong> {{ finding.confidence }} &nbsp;|&nbsp;{% endif %}
            {% if finding.cwe_id %}<strong>CWE:</strong> {{ finding.cwe_id }}{% endif %}
        </div>

        {% if finding.description %}
        <p>{{ finding.description }}</p>
        {% endif %}

        {% if finding.code_snippet %}
        <pre>{{ finding.code_snippet }}</pre>
        {% endif %}

        {% if finding.recommendation %}
        <div class="recommendation">
            <strong>Recommendation:</strong> {{ finding.recommendation }}
        </div>
        {% endif %}
    </div>
    {% endfor %}

    {% endif %}

    <!-- ============ AI COST FORECAST ============ -->
    {% if data.cost_forecast %}
    <h2>💡 AI Full-Scan Cost Forecast</h2>
    <p style="color:#64748b;font-size:14px;margin-bottom:16px">
        Estimated cost to run a <strong>complete AI analysis</strong> of the entire repository
        with each configured model. Based on
        <strong>{{ data.cost_forecast[0].total_files }} files</strong> /
        <strong>{{ "{:,}".format(data.cost_forecast[0].total_code_tokens) }} code tokens</strong> /
        <strong>{{ data.cost_forecast[0].estimated_chunks }} chunks</strong>.
    </p>
    <table>
        <thead>
            <tr>
                <th>Model</th>
                <th>Provider</th>
                <th>Input price<br><small>$/1M tok</small></th>
                <th>Output price<br><small>$/1M tok</small></th>
                <th>Est. input tokens</th>
                <th>Est. output tokens</th>
                <th style="font-size:15px">Est. total cost</th>
                <th>Budget limit</th>
                <th>Fits budget?</th>
            </tr>
        </thead>
        <tbody>
        {% for fc in data.cost_forecast %}
            <tr>
                <td><strong>{{ fc.model_name }}</strong><br><span style="font-family:monospace;font-size:11px;color:#94a3b8">{{ fc.model_id }}</span></td>
                <td>{{ fc.provider }}</td>
                <td style="text-align:right">${{ "%.2f"|format(fc.input_price_per_mtok) }}</td>
                <td style="text-align:right">${{ "%.2f"|format(fc.output_price_per_mtok) }}</td>
                <td style="text-align:right">{{ "{:,}".format(fc.estimated_input_tokens) }}</td>
                <td style="text-align:right">{{ "{:,}".format(fc.estimated_output_tokens) }}</td>
                <td style="text-align:right;font-weight:bold;font-size:15px">
                    ${{ "%.4f"|format(fc.estimated_total_cost_usd) }}
                </td>
                <td style="text-align:right">${{ "%.2f"|format(fc.max_budget_usd) }}</td>
                <td style="text-align:center">
                    {% if fc.within_budget %}
                    <span style="color:#16a34a;font-weight:bold">✓ Yes</span>
                    {% else %}
                    <span style="color:#dc2626;font-weight:bold">✗ Exceeds</span>
                    {% endif %}
                </td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
    <p style="color:#94a3b8;font-size:12px;margin-top:8px">
        ⚠️ Forecast is based on ~4 chars/token estimation and assumes ~20% output ratio.
        Actual cost may vary. Cheaper models may miss subtle logic vulnerabilities.
    </p>
    {% endif %}

    <!-- ============ TOKEN USAGE BREAKDOWN (actual, if AI scan ran) ============ -->
    {% if data.token_breakdown %}
    <h2>Token Usage Breakdown (Actual)</h2>
    <table>
        <thead>
            <tr>
                <th>Chunk</th>
                <th style="text-align:right">Input tokens</th>
                <th style="text-align:right">Output tokens</th>
                <th style="text-align:right">Cost (USD)</th>
            </tr>
        </thead>
        <tbody>
        {% for row in data.token_breakdown %}
            <tr>
                <td>{{ row.chunk }}</td>
                <td style="text-align:right">{{ "{:,}".format(row.input_tokens) }}</td>
                <td style="text-align:right">{{ "{:,}".format(row.output_tokens) }}</td>
                <td style="text-align:right">${{ "%.6f"|format(row.cost_usd) }}</td>
            </tr>
        {% endfor %}
        </tbody>
        <tfoot>
            <tr style="font-weight:bold;background:#f8fafc">
                <td>TOTAL</td>
                <td style="text-align:right">{{ "{:,}".format(data.scan.tokens_used or 0) }}</td>
                <td style="text-align:right">—</td>
                <td style="text-align:right">${{ "%.6f"|format(data.scan.cost_usd or 0) }}</td>
            </tr>
        </tfoot>
    </table>
    {% endif %}

    <div class="footer">
        Generated by AISO (AI-Driven Security Orchestrator) &mdash; {{ generated_at }}
    </div>

</div>
</body>
</html>
"""

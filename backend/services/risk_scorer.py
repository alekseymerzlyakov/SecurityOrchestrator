"""Risk scoring engine for security findings.

Provides two levels of scoring:
1. Individual finding scoring (0-10 scale based on CVSS/severity/confidence).
2. Project-level aggregate scoring (0-100 scale, where 100 = no issues).
"""

import logging
from collections import Counter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity mappings
# ---------------------------------------------------------------------------

SEVERITY_BASE_SCORES: dict[str, float] = {
    "critical": 9.5,
    "high": 7.5,
    "medium": 5.0,
    "low": 2.5,
    "info": 1.0,
}

CONFIDENCE_MULTIPLIERS: dict[str, float] = {
    "high": 1.0,
    "medium": 0.8,
    "low": 0.6,
}

# Weights for project-level scoring: how much each severity contributes
SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 10.0,
    "high": 5.0,
    "medium": 2.0,
    "low": 0.5,
    "info": 0.1,
}

# Grade thresholds (score out of 100)
GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]

RISK_LEVEL_THRESHOLDS: list[tuple[float, str]] = [
    (90, "low"),
    (70, "moderate"),
    (50, "elevated"),
    (30, "high"),
    (0, "critical"),
]


# ---------------------------------------------------------------------------
# Finding-level scoring
# ---------------------------------------------------------------------------

def score_finding(finding: dict) -> float:
    """Calculate a risk score for an individual finding.

    Scoring logic:
    1. If a CVSS score is provided, use it as the base.
    2. Otherwise, map severity to a base score.
    3. Apply a confidence multiplier.
    4. Clamp the result to [0, 10].

    Args:
        finding: Dict with optional keys: cvss_score, severity, confidence.

    Returns:
        Risk score between 0.0 and 10.0.
    """
    # Base score: prefer explicit CVSS
    cvss = finding.get("cvss_score")
    if cvss is not None and isinstance(cvss, (int, float)) and 0 <= cvss <= 10:
        base_score = float(cvss)
    else:
        severity = (finding.get("severity") or "medium").lower()
        base_score = SEVERITY_BASE_SCORES.get(severity, 5.0)

    # Confidence multiplier
    confidence = (finding.get("confidence") or "medium").lower()
    multiplier = CONFIDENCE_MULTIPLIERS.get(confidence, 0.8)

    score = base_score * multiplier

    # Clamp to [0, 10]
    return round(max(0.0, min(10.0, score)), 2)


# ---------------------------------------------------------------------------
# Project-level scoring
# ---------------------------------------------------------------------------

def score_project(findings: list[dict]) -> dict:
    """Calculate an aggregate project security score.

    Scoring formula:
    - Start at 100 (perfect score, no issues).
    - Subtract weighted finding scores where critical findings have
      disproportionate impact.
    - Clamp to [0, 100].

    Args:
        findings: List of finding dicts.

    Returns:
        {
            "score": float (0-100),
            "grade": str (A-F),
            "risk_level": str (low/moderate/elevated/high/critical),
            "severity_counts": {"critical": N, "high": N, ...},
            "total_findings": int,
            "weighted_deduction": float,
            "findings_by_confidence": {"high": N, "medium": N, "low": N},
        }
    """
    if not findings:
        return {
            "score": 100.0,
            "grade": "A",
            "risk_level": "low",
            "severity_counts": {},
            "total_findings": 0,
            "weighted_deduction": 0.0,
            "findings_by_confidence": {},
        }

    # Count severities
    severity_counts: Counter = Counter()
    confidence_counts: Counter = Counter()
    total_deduction = 0.0

    for finding in findings:
        severity = (finding.get("severity") or "medium").lower()
        confidence = (finding.get("confidence") or "medium").lower()

        severity_counts[severity] += 1
        confidence_counts[confidence] += 1

        # Get the finding's individual score
        finding_score = score_finding(finding)

        # Weight by severity for disproportionate impact of critical findings
        weight = SEVERITY_WEIGHTS.get(severity, 2.0)
        total_deduction += finding_score * weight / 10.0  # Normalize: 10.0 max score

    # Calculate final project score
    project_score = 100.0 - min(100.0, total_deduction)
    project_score = round(max(0.0, project_score), 1)

    # Determine grade
    grade = "F"
    for threshold, letter in GRADE_THRESHOLDS:
        if project_score >= threshold:
            grade = letter
            break

    # Determine risk level
    risk_level = "critical"
    for threshold, level in RISK_LEVEL_THRESHOLDS:
        if project_score >= threshold:
            risk_level = level
            break

    return {
        "score": project_score,
        "grade": grade,
        "risk_level": risk_level,
        "severity_counts": dict(severity_counts),
        "total_findings": len(findings),
        "weighted_deduction": round(total_deduction, 2),
        "findings_by_confidence": dict(confidence_counts),
    }

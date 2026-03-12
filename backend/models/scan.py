"""Scan-related models: Scan, ScanStep, Finding, TokenUsage."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from backend.database import Base


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    branch = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending/running/completed/stopped/failed
    mode = Column(String, default="hybrid")  # hybrid/tools_only/ai_only
    pipeline_json = Column(Text, nullable=True)  # ordered list of steps
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    total_files = Column(Integer, default=0)
    files_processed = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    estimated_total_tokens = Column(Integer, nullable=True)
    estimated_total_cost = Column(Float, nullable=True)
    ai_summary = Column(Text, nullable=True)         # cached AI executive summary (Markdown)
    ai_summary_at = Column(DateTime, nullable=True)  # when it was generated


class ScanStep(Base):
    __tablename__ = "scan_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    step_order = Column(Integer, nullable=False)
    tool_name = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending/running/completed/failed/skipped
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    files_processed = Column(Integer, default=0)
    findings_count = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)


class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    scan_step_id = Column(Integer, ForeignKey("scan_steps.id"), nullable=True)
    type = Column(String, nullable=True)  # xss, injection, secret, dependency, auth, config
    severity = Column(String, nullable=True)  # critical, high, medium, low, info
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String, nullable=True)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    code_snippet = Column(Text, nullable=True)
    tool_name = Column(String, nullable=True)
    confidence = Column(String, nullable=True)  # high, medium, low
    cvss_score = Column(Float, nullable=True)
    cwe_id = Column(String, nullable=True)
    recommendation = Column(Text, nullable=True)
    commit_author = Column(String, nullable=True)
    commit_date = Column(String, nullable=True)
    status = Column(String, default="open")  # open/in_progress/fixed/false_positive
    jira_ticket_id = Column(String, nullable=True)
    jira_ticket_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    model_id = Column(Integer, ForeignKey("ai_models.id"), nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    chunk_description = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

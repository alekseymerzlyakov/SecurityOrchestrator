"""Settings models: AI Providers, AI Models, Tool Configs, Jira Config."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from backend.database import Base


class AIProvider(Base):
    __tablename__ = "ai_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)  # "Anthropic", "OpenAI", etc.
    provider_type = Column(String, nullable=False)  # "anthropic", "openai", "google", "ollama"
    api_key = Column(String, nullable=True)  # encrypted
    base_url = Column(String, nullable=True)  # custom endpoint
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AIModel(Base):
    __tablename__ = "ai_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=False)
    name = Column(String, nullable=False)  # "Claude Opus 4.6"
    model_id = Column(String, nullable=False)  # "claude-opus-4-6"
    max_tokens_per_run = Column(Integer, default=1000000)
    max_budget_usd = Column(Float, default=50.0)
    context_window = Column(Integer, nullable=True)
    input_price_per_mtok = Column(Float, nullable=True)
    output_price_per_mtok = Column(Float, nullable=True)
    requests_per_minute = Column(Integer, nullable=True)  # RPM limit for throttling (None = no limit)
    is_active = Column(Boolean, default=True)


class ToolConfig(Base):
    __tablename__ = "tool_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_name = Column(String, nullable=False, unique=True)
    is_enabled = Column(Boolean, default=True)
    config_json = Column(Text, default="{}")
    install_command = Column(String, nullable=True)
    version = Column(String, nullable=True)


class JiraConfig(Base):
    __tablename__ = "jira_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    base_url = Column(String, nullable=False)
    api_token = Column(String, nullable=True)  # encrypted
    user_email = Column(String, nullable=True)
    project_key = Column(String, nullable=False)
    issue_type = Column(String, default="Bug")
    priority_mapping = Column(Text, default='{"critical":"Highest","high":"High","medium":"Medium","low":"Low"}')
    is_active = Column(Boolean, default=True)

"""Application configuration."""

import os
from pathlib import Path
from cryptography.fernet import Fernet

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "aiso.db"
PROMPTS_DIR = Path(__file__).parent / "prompts"
TEMPLATES_DIR = Path(__file__).parent / "templates"
REPORTS_DIR = DATA_DIR / "reports"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# Database
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# Server
HOST = "0.0.0.0"
PORT = 8000
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Encryption key for API keys (generate once, store in env or file)
_key_file = DATA_DIR / ".encryption_key"
if _key_file.exists():
    ENCRYPTION_KEY = _key_file.read_bytes()
else:
    ENCRYPTION_KEY = Fernet.generate_key()
    _key_file.write_bytes(ENCRYPTION_KEY)
    os.chmod(_key_file, 0o600)

_fernet = Fernet(ENCRYPTION_KEY)


def encrypt_value(value: str) -> str:
    """Encrypt a string value (e.g., API key)."""
    return _fernet.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt an encrypted string value."""
    return _fernet.decrypt(encrypted.encode()).decode()


# Default AI model pricing ($/1M tokens)
DEFAULT_MODEL_PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "context_window": 200000},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0, "context_window": 200000},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0, "context_window": 200000},
    "gpt-4o": {"input": 2.50, "output": 10.0, "context_window": 128000},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "context_window": 128000},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0, "context_window": 128000},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "context_window": 1000000},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0, "context_window": 2000000},
}

# Default tool configurations
DEFAULT_TOOLS = [
    {
        "tool_name": "semgrep",
        "install_command": "pip install semgrep",
        "config_json": '{"rules": "auto"}',
    },
    {
        "tool_name": "gitleaks",
        "install_command": "brew install gitleaks",
        "config_json": "{}",
    },
    {
        "tool_name": "trivy",
        "install_command": "brew install trivy",
        "config_json": '{"scan_type": "fs"}',
    },
    {
        "tool_name": "npm_audit",
        "install_command": "",
        "config_json": "{}",
    },
    {
        "tool_name": "eslint_security",
        "install_command": "npm install -g eslint eslint-plugin-security eslint-plugin-no-unsanitized",
        "config_json": "{}",
    },
    {
        "tool_name": "retirejs",
        "install_command": "npm install -g retire",
        "config_json": "{}",
    },
]

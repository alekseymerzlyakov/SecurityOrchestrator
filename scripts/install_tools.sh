#!/bin/bash
# AISO — Install security scanning tools
# Run: chmod +x scripts/install_tools.sh && ./scripts/install_tools.sh

set -e

echo "=== AISO Security Tools Installer ==="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_and_install() {
    local name=$1
    local check_cmd=$2
    local install_cmd=$3

    if command -v "$check_cmd" &> /dev/null; then
        local version=$($check_cmd --version 2>/dev/null | head -1 || echo "installed")
        echo -e "${GREEN}✓${NC} $name already installed: $version"
    else
        echo -e "${YELLOW}→${NC} Installing $name..."
        eval "$install_cmd"
        if command -v "$check_cmd" &> /dev/null; then
            echo -e "${GREEN}✓${NC} $name installed successfully"
        else
            echo -e "${RED}✗${NC} Failed to install $name"
        fi
    fi
}

# Check Homebrew
if ! command -v brew &> /dev/null; then
    echo -e "${RED}✗${NC} Homebrew not found. Install it first: https://brew.sh"
    exit 1
fi
echo -e "${GREEN}✓${NC} Homebrew found"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}✗${NC} pip3 not found. Install Python first."
    exit 1
fi
echo -e "${GREEN}✓${NC} pip3 found"

# Check npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}✗${NC} npm not found. Install Node.js first."
    exit 1
fi
echo -e "${GREEN}✓${NC} npm found"

echo ""
echo "--- SAST Tools ---"

# Semgrep (SAST)
check_and_install "Semgrep" "semgrep" "pip3 install semgrep"

# ESLint + security plugins (global)
if npm list -g eslint &> /dev/null; then
    echo -e "${GREEN}✓${NC} ESLint already installed globally"
else
    echo -e "${YELLOW}→${NC} Installing ESLint + security plugins..."
    npm install -g eslint eslint-plugin-security eslint-plugin-no-unsanitized
    echo -e "${GREEN}✓${NC} ESLint + security plugins installed"
fi

echo ""
echo "--- Secret Scanning ---"

# Gitleaks
check_and_install "Gitleaks" "gitleaks" "brew install gitleaks"

echo ""
echo "--- Dependency Scanning ---"

# Trivy
check_and_install "Trivy" "trivy" "brew install trivy"

# RetireJS
check_and_install "RetireJS" "retire" "npm install -g retire"

# npm audit is built-in with npm
echo -e "${GREEN}✓${NC} npm audit (built-in with npm)"

echo ""
echo "--- Python Backend Dependencies ---"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_DIR/backend/requirements.txt" ]; then
    echo -e "${YELLOW}→${NC} Installing Python backend dependencies..."
    cd "$PROJECT_DIR"

    # Create virtual environment if not exists
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        echo -e "${GREEN}✓${NC} Virtual environment created"
    fi

    source venv/bin/activate
    pip install -r backend/requirements.txt
    echo -e "${GREEN}✓${NC} Python dependencies installed"
else
    echo -e "${RED}✗${NC} backend/requirements.txt not found"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Installed tools summary:"
echo "  - Semgrep (SAST)"
echo "  - ESLint + security plugins (JS security linting)"
echo "  - Gitleaks (secret scanning)"
echo "  - Trivy (dependency vulnerabilities)"
echo "  - RetireJS (vulnerable JS libraries)"
echo "  - npm audit (built-in)"
echo ""
echo "To start the backend:"
echo "  cd $PROJECT_DIR && source venv/bin/activate"
echo "  cd backend && uvicorn main:app --reload --port 8000"

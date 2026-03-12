#!/bin/bash
# AISO — Full project setup
# Run: chmod +x scripts/setup.sh && ./scripts/setup.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== AISO Project Setup ==="
echo "Project directory: $PROJECT_DIR"
echo ""

# 1. Install security tools
echo -e "${YELLOW}Step 1: Installing security tools...${NC}"
bash "$SCRIPT_DIR/install_tools.sh"
echo ""

# 2. Setup frontend
echo -e "${YELLOW}Step 2: Setting up frontend...${NC}"
cd "$PROJECT_DIR/frontend"
if [ -f "package.json" ]; then
    npm install
    echo -e "${GREEN}✓${NC} Frontend dependencies installed"
else
    echo -e "${YELLOW}!${NC} frontend/package.json not found, skipping"
fi
echo ""

# 3. Create data directories
echo -e "${YELLOW}Step 3: Creating data directories...${NC}"
mkdir -p "$PROJECT_DIR/data/reports"
echo -e "${GREEN}✓${NC} Data directories ready"

# 4. Initialize database
echo -e "${YELLOW}Step 4: Initializing database...${NC}"
cd "$PROJECT_DIR"
source venv/bin/activate
python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from backend.database import init_db
asyncio.run(init_db())
print('Database initialized successfully')
"
echo -e "${GREEN}✓${NC} Database initialized"

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "To start the application:"
echo ""
echo "  Terminal 1 (Backend):"
echo "    cd $PROJECT_DIR"
echo "    source venv/bin/activate"
echo "    uvicorn backend.main:app --reload --port 8000"
echo ""
echo "  Terminal 2 (Frontend):"
echo "    cd $PROJECT_DIR/frontend"
echo "    npm run dev"
echo ""
echo "  Then open: http://localhost:5173"
echo "  API docs: http://localhost:8000/docs"

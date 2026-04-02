#!/bin/bash
#
# GitLab Opencode Reviewer - Startup Script
#

set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$INSTALL_DIR/venv"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Starting GitLab Opencode Reviewer...${NC}"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Please run ./install.sh first"
    exit 1
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Load environment variables
if [ -f "$INSTALL_DIR/.env" ]; then
    export $(grep -v '^#' "$INSTALL_DIR/.env" | xargs)
fi

# Check if opencode is in PATH
if [ -d "$HOME/.opencode/bin" ]; then
    export PATH="$HOME/.opencode/bin:$PATH"
fi

# Verify opencode is available
if ! command -v opencode &> /dev/null; then
    echo "Error: opencode not found in PATH"
    echo "Please ensure opencode is installed and in your PATH"
    exit 1
fi

echo -e "${GREEN}✓ Opencode version:${NC} $(opencode --version)"
echo -e "${GREEN}✓ Python version:${NC} $(python --version)"
echo ""

# Run the application
cd "$INSTALL_DIR"
exec python src/main.py

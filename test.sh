#!/bin/bash
#
# GitLab Opencode Reviewer - Test Script
#

set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$INSTALL_DIR/venv"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Running tests...${NC}"

# Activate virtual environment
source "$VENV_DIR/bin/activate"

cd "$INSTALL_DIR"

echo -e "${YELLOW}1. Testing imports...${NC}"
python -c "from src.logger import get_logger; from src.config import get_config; print('✓ Imports OK')"

echo -e "${YELLOW}2. Testing configuration...${NC}"
python -c "from src.config import get_config; c = get_config(); print(f'✓ Config loaded: {c.to_dict()}')"

echo -e "${YELLOW}3. Testing logger...${NC}"
python -c "from src.logger import get_logger; l = get_logger('test'); l.info('✓ Logger works')"

echo ""
echo -e "${GREEN}All tests passed!${NC}"

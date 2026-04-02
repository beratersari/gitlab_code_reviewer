#!/bin/bash
#
# GitLab Opencode Reviewer - Installation Script
#
# This script installs:
# 1. Python 3.11+ (if not present)
# 2. Required Python packages
# 3. Opencode CLI tool
# 4. Sets up the application environment
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$INSTALL_DIR/venv"
LOGS_DIR="$INSTALL_DIR/logs"
TEMP_DIR="/tmp/gitlab-reviewer"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python version
check_python() {
    log_info "Checking Python installation..."
    
    if command_exists python3; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        log_info "Found Python $PYTHON_VERSION"
        
        # Check if version is 3.11+
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
            log_success "Python version is compatible (3.11+)"
            PYTHON_CMD="python3"
        else
            log_error "Python 3.11+ is required but found $PYTHON_VERSION"
            log_info "Please install Python 3.11 or higher"
            exit 1
        fi
    else
        log_error "Python 3 is not installed"
        log_info "Please install Python 3.11 or higher from https://www.python.org/"
        exit 1
    fi
}

# Install opencode CLI
install_opencode() {
    log_info "Installing Opencode CLI..."
    
    if command_exists opencode; then
        OPCODE_VERSION=$(opencode --version 2>&1 || echo "unknown")
        log_success "Opencode is already installed: $OPCODE_VERSION"
        return 0
    fi
    
    log_info "Downloading and installing opencode..."
    
    # Try multiple installation methods
    if curl -fsSL https://opencode.ai/install | bash; then
        log_success "Opencode installed successfully"
        
        # Add to PATH if needed
        if [ -d "$HOME/.opencode/bin" ]; then
            export PATH="$HOME/.opencode/bin:$PATH"
            log_info "Added ~/.opencode/bin to PATH"
            
            # Add to shell profile for persistence
            SHELL_PROFILE=""
            if [ -f "$HOME/.bashrc" ]; then
                SHELL_PROFILE="$HOME/.bashrc"
            elif [ -f "$HOME/.zshrc" ]; then
                SHELL_PROFILE="$HOME/.zshrc"
            fi
            
            if [ -n "$SHELL_PROFILE" ] && ! grep -q "opencode/bin" "$SHELL_PROFILE"; then
                echo 'export PATH="$HOME/.opencode/bin:$PATH"' >> "$SHELL_PROFILE"
                log_info "Added opencode to PATH in $SHELL_PROFILE"
            fi
        fi
    else
        log_error "Failed to install opencode"
        log_info "You can manually install from: https://opencode.ai"
        exit 1
    fi
}

# Setup Python virtual environment
setup_venv() {
    log_info "Setting up Python virtual environment..."
    
    if [ -d "$VENV_DIR" ]; then
        log_warning "Virtual environment already exists at $VENV_DIR"
        read -p "Recreate? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
        fi
    fi
    
    if [ ! -d "$VENV_DIR" ]; then
        $PYTHON_CMD -m venv "$VENV_DIR"
        log_success "Created virtual environment at $VENV_DIR"
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    log_info "Activated virtual environment"
    
    # Upgrade pip
    pip install --upgrade pip setuptools wheel
    log_success "Upgraded pip"
}

# Install Python dependencies
install_python_deps() {
    log_info "Installing Python dependencies..."
    
    # Create requirements.txt if it doesn't exist
    REQUIREMENTS_FILE="$INSTALL_DIR/requirements.txt"
    
    if [ ! -f "$REQUIREMENTS_FILE" ]; then
        log_info "Creating requirements.txt..."
        cat > "$REQUIREMENTS_FILE" << 'EOF'
# Web Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0

# HTTP Client
requests==2.31.0

# GitLab API
python-gitlab==4.2.0

# Git operations
GitPython==3.1.40

# Utilities
python-dotenv==1.0.0
EOF
    fi
    
    pip install -r "$REQUIREMENTS_FILE"
    log_success "Installed Python dependencies"
}

# Create necessary directories
create_directories() {
    log_info "Creating application directories..."
    
    mkdir -p "$LOGS_DIR"
    mkdir -p "$TEMP_DIR"
    
    log_success "Created directories:"
    log_info "  - Logs: $LOGS_DIR"
    log_info "  - Temp: $TEMP_DIR"
}

# Create environment file
create_env_file() {
    ENV_FILE="$INSTALL_DIR/.env"
    
    if [ -f "$ENV_FILE" ]; then
        log_warning ".env file already exists"
        return 0
    fi
    
    log_info "Creating environment configuration file..."
    
    cat > "$ENV_FILE" << EOF
# GitLab Opencode Reviewer Configuration
# Generated on $(date)

# Server Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# GitLab Configuration
# Get your token from: GitLab -> User Settings -> Access Tokens
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=your_gitlab_token_here

# Webhook Security (optional but recommended)
# Set this secret in your GitLab webhook configuration
WEBHOOK_SECRET=your_webhook_secret_here

# Opencode Configuration
# Format: provider/model-name
# Use opencode/big-pickle for local testing (no API key required)
OPENCODE_MODEL=opencode/big-pickle
OPENCODE_TIMEOUT=300

# Review Configuration
# Comma-separated list of file extensions to review
REVIEW_EXTENSIONS=.py,.js,.ts,.java,.go,.rs,.cpp,.c,.h,.rb,.php,.cs,.swift,.kt
MAX_FILE_SIZE_KB=500

# Paths (usually don't need to change)
TEMP_DIR=$TEMP_DIR

# Simulation Mode (for testing without GitLab)
# Set to "true" to use local sample_project instead of real GitLab
SIMULATION_MODE=false
EOF
    
    log_success "Created .env file at $ENV_FILE"
    log_warning "⚠️  IMPORTANT: Edit .env file and set your GITLAB_TOKEN and other configurations"
}

# Create startup script
create_startup_script() {
    STARTUP_SCRIPT="$INSTALL_DIR/start.sh"
    
    log_info "Creating startup script..."
    
    cat > "$STARTUP_SCRIPT" << 'EOF'
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
EOF
    
    chmod +x "$STARTUP_SCRIPT"
    log_success "Created startup script at $STARTUP_SCRIPT"
}

# Create test script
create_test_script() {
    TEST_SCRIPT="$INSTALL_DIR/test.sh"
    
    log_info "Creating test script..."
    
    cat > "$TEST_SCRIPT" << 'EOF'
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
EOF
    
    chmod +x "$TEST_SCRIPT"
    log_success "Created test script at $TEST_SCRIPT"
}

# Print final instructions
print_instructions() {
    echo ""
    echo "========================================"
    echo "  Installation Complete!"
    echo "========================================"
    echo ""
    echo -e "${GREEN}Next steps:${NC}"
    echo ""
    echo "1. Configure the application:"
    echo "   Edit the .env file and set your:"
    echo "   - GITLAB_TOKEN (required for production)"
    echo "   - WEBHOOK_SECRET (recommended)"
    echo "   - OPENCODE_MODEL (if you want a different model)"
    echo ""
    echo "2. Test the installation:"
    echo "   ./test.sh"
    echo ""
    echo "3. Start the server:"
    echo "   ./start.sh"
    echo ""
    echo "4. Test with mock webhook (in another terminal):"
    echo "   python tests/mock_gitlab_server.py"
    echo ""
    echo "5. Or trigger a test review directly:"
    echo "   curl -X POST http://localhost:8000/test-review"
    echo ""
    echo "Logs will be saved to: $LOGS_DIR"
    echo ""
    echo -e "${YELLOW}For production use:${NC}"
    echo "- Set up a reverse proxy (nginx/caddy)"
    echo "- Configure GitLab webhook pointing to your server"
    echo "- Use systemd or supervisor to run as a service"
    echo ""
}

# Main installation flow
main() {
    echo "========================================"
    echo "  GitLab Opencode Reviewer Installer"
    echo "========================================"
    echo ""
    
    log_info "Installation directory: $INSTALL_DIR"
    
    # Run installation steps
    check_python
    install_opencode
    setup_venv
    install_python_deps
    create_directories
    create_env_file
    create_startup_script
    create_test_script
    
    # Make mock server executable
    chmod +x "$INSTALL_DIR/tests/mock_gitlab_server.py"
    
    print_instructions
}

# Run main function
main "$@"

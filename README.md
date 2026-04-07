# GitLab Opencode Reviewer

An automated code review system that integrates GitLab merge requests with the [Opencode](https://opencode.ai) AI coding agent. The system clones repositories, loads project-specific review rules, and provides intelligent code reviews on merge requests.

## Features

- 🤖 **AI-Powered Reviews**: Uses Opencode AI to analyze code changes
- 📋 **Project-Specific Rules**: Loads `agent/rules/CODE_REVIEW.md` from each repository
- 🔄 **GitLab Integration**: Responds to MR webhooks (open, update, comments)
- 📝 **Structured Logging**: Comprehensive logging with datetime, level, file/line, and context
- 🧪 **Mock Testing**: Test without real GitLab using the mock server
- 🐍 **Python-Based**: Easy to extend and customize

## Architecture

```
GitLab Webhook → FastAPI Server → Clone Repo → Load Rules → Opencode Review → Post Comment
```

## Quick Start

### Prerequisites

- Python 3.11+
- Git
- curl

### Installation

1. **Clone or download this repository:**
   ```bash
   cd gitlab-opencode-reviewer
   ```

2. **Run the installation script:**
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

   This will:
   - Check Python version
   - Install Opencode CLI
   - Create a Python virtual environment
   - Install Python dependencies
   - Create configuration files
   - Set up startup scripts

3. **Configure the application:**
   ```bash
   # Edit the .env file with your settings
   nano .env
   ```

   Minimum required for testing:
   ```env
   # For production GitLab integration
   GITLAB_TOKEN=your_gitlab_token
   WEBHOOK_SECRET=your_webhook_secret
   
   # Opencode model (default is usually fine)
   OPENCODE_MODEL=anthropic/claude-sonnet-4-20250514
   ```

### Running the System

1. **Start the reviewer server:**
   ```bash
   ./start.sh
   ```

   You should see output like:
   ```
   [2024-01-15 10:30:25.123] [INFO    ] [main.py:42                    ] ============================================================
   [2024-01-15 10:30:25.124] [INFO    ] [main.py:43                    ] GitLab Opencode Reviewer Starting
   [2024-01-15 10:30:25.125] [INFO    ] [main.py:44                    ] ============================================================
   ```

2. **Test with mock webhook (in another terminal):**
   ```bash
   # Interactive mode
   python tests/mock_gitlab_server.py

   # Or non-interactive
   python tests/mock_gitlab_server.py --event mr-open
   ```

3. **Or trigger test review via curl:**
   ```bash
   curl -X POST http://localhost:8000/test-review
   ```

## Project Structure

```
gitlab-opencode-reviewer/
├── src/
│   ├── main.py              # FastAPI application and webhook handler
│   ├── logger.py            # Structured logging system
│   ├── config.py            # Configuration management
│   ├── gitlab_client.py     # GitLab API client + Mock client
│   └── opencode_wrapper.py  # Opencode CLI wrapper
├── tests/
│   └── mock_gitlab_server.py # Mock GitLab for testing
├── sample_project/
│   └── agent/
│       └── rules/
│           └── CODE_REVIEW.md # Example review rules
├── logs/                    # Log files (created at runtime)
│   ├── app.log             # Human-readable logs
│   └── app.jsonl           # JSON logs for parsing
├── install.sh              # Installation script
├── start.sh                # Startup script
├── test.sh                 # Test script
├── requirements.txt        # Python dependencies (no Rust required)
└── .env                    # Configuration (created by install.sh)
```

## Configuration

All configuration is done via environment variables in the `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `GITLAB_URL` | `https://gitlab.com` | GitLab instance URL |
| `GITLAB_TOKEN` | - | GitLab personal access token |
| `WEBHOOK_SECRET` | - | Secret for webhook validation |
| `OPENCODE_MODEL` | `anthropic/claude-sonnet-4-20250514` | AI model to use |
| `OPENCODE_TIMEOUT` | `300` | Review timeout in seconds |
| `REVIEW_EXTENSIONS` | `.py,.js,.ts,...` | File extensions to review |
| `MAX_FILE_SIZE_KB` | `500` | Skip files larger than this |

## Dependencies

All dependencies are pure Python (no Rust required):

- **fastapi** - Web framework
- **uvicorn** - ASGI server
- **requests** - HTTP client
- **python-gitlab** - GitLab API client
- **GitPython** - Git operations
- **python-dotenv** - Environment variable management

## Logging System

The system provides comprehensive structured logging:

### Console Output (with colors)
```
[2024-01-15 10:30:25.123] [INFO    ] [main.py:42                    ] ============================================================
[2024-01-15 10:30:25.124] [INFO    ] [main.py:43                    ] GitLab Opencode Reviewer Starting
[2024-01-15 10:30:25.200] [INFO    ] [main.py:44                    ] FLOW: review_workflow_start | flow_project_id=123 flow_mr_iid=1 flow_use_mock=False
```

### Log Files

1. **logs/app.log** - Human-readable text format
2. **logs/app.jsonl** - Machine-readable JSON format

Each log entry includes:
- **Timestamp**: `2024-01-15 10:30:25.123`
- **Log Level**: `INFO`, `DEBUG`, `WARNING`, `ERROR`
- **File and Line**: `main.py:42`
- **Context Fields**: `flow_project_id`, `flow_step`, etc.

### Viewing Logs

```bash
# Follow logs in real-time
tail -f logs/app.log

# Search for specific flow steps
grep "FLOW: review_workflow" logs/app.log

# Parse JSON logs
jq -r 'select(.flow_step == "review_file_start") | .' logs/app.jsonl
```

## Project-Specific Review Rules

Each project can define custom review rules by creating:

```
agent/rules/CODE_REVIEW.md
```

Example rules file (see `sample_project/agent/rules/CODE_REVIEW.md`):

```markdown
# Code Review Guidelines

## Python Standards

### Type Hints
- All function parameters must have type hints
- Return types must be explicitly declared

### Error Handling
- Never use bare `except:` clauses
- Always catch specific exceptions

### Security
- Validate all user inputs
- Never log sensitive data (passwords, tokens, PII)
```

These rules are automatically loaded when reviewing a repository and injected into the AI prompt.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check and stats |
| `/webhook` | POST | Receive GitLab webhooks |
| `/test-review` | POST | Trigger test review with mock data |
| `/config` | GET | View current configuration |

## Webhook Events

The system responds to these GitLab webhook events:

### Merge Request Hook
- `open` - New MR created
- `update` - New commits pushed to MR
- `reopen` - Closed MR reopened

### Note Hook
- Comments containing `/review` trigger a review

## Mock Server Usage

The mock server allows testing without real GitLab access:

```bash
# Interactive mode (menu-driven)
python tests/mock_gitlab_server.py

# Non-interactive: Trigger MR open event
python tests/mock_gitlab_server.py --event mr-open --project-id 123 --mr-iid 1

# Non-interactive: Trigger MR update
python tests/mock_gitlab_server.py --event mr-update

# Non-interactive: Trigger comment with /review
python tests/mock_gitlab_server.py --event mr-comment

# Custom reviewer URL
python tests/mock_gitlab_server.py -u http://localhost:9000

# With webhook secret
python tests/mock_gitlab_server.py -s my-secret-token
```

### Mock Server Interactive Menu

```
============================================================
GitLab Mock Webhook Server - Interactive Mode
============================================================

Options:
1. Trigger MR Open event
2. Trigger MR Update event
3. Trigger MR Comment (/review)
4. Trigger custom comment
5. Test connection
6. Exit

Select option [1-6]:
```

## GitLab Webhook Configuration

For production use with real GitLab:

1. Go to **Project Settings → Webhooks**
2. Add URL: `http://your-server:8000/webhook`
3. Set Secret Token (match `WEBHOOK_SECRET` in .env)
4. Select events:
   - ✅ Merge request events
   - ✅ Comments
5. Add webhook

## Production Deployment

### Using systemd

Create `/etc/systemd/system/gitlab-reviewer.service`:

```ini
[Unit]
Description=GitLab Opencode Reviewer
After=network.target

[Service]
Type=simple
User=gitlab-reviewer
WorkingDirectory=/opt/gitlab-opencode-reviewer
ExecStart=/opt/gitlab-opencode-reviewer/start.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable gitlab-reviewer
sudo systemctl start gitlab-reviewer
sudo systemctl status gitlab-reviewer
```

### Using Docker (Optional)

While you requested no Dockerfile, here's a simple alternative using systemd:

```bash
# Install as user service
mkdir -p ~/.config/systemd/user
cp /etc/systemd/system/gitlab-reviewer.service ~/.config/systemd/user/
systemctl --user enable gitlab-reviewer
systemctl --user start gitlab-reviewer
```

### Reverse Proxy (nginx)

```nginx
server {
    listen 80;
    server_name reviewer.example.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Gitlab-Token $http_x_gitlab_token;
    }
}
```

## Troubleshooting

### Opencode Not Found
```bash
# Add to PATH
export PATH="$HOME/.opencode/bin:$PATH"

# Or reinstall
./install.sh
```

### Permission Denied
```bash
chmod +x install.sh start.sh test.sh
```

### Virtual Environment Issues
```bash
# Recreate venv
rm -rf venv
./install.sh
```

### Check Logs for Errors
```bash
# Recent errors
grep "ERROR" logs/app.log | tail -20

# Specific flow step issues
grep "review_workflow" logs/app.log
```

### Test Configuration
```bash
# View current config
curl http://localhost:8000/config

# Test health
curl http://localhost:8000/health
```

## Development

### Adding New Features

1. **Modify src/main.py** for webhook handling
2. **Modify src/opencode_wrapper.py** for review logic
3. **Modify src/gitlab_client.py** for GitLab API operations

### Running Tests

```bash
./test.sh
```

### Manual Testing

```bash
# Start server in one terminal
./start.sh

# Trigger test in another terminal
curl -X POST http://localhost:8000/test-review

# Check logs
tail -f logs/app.log
```

## Architecture Flow

```
1. GitLab sends webhook → POST /webhook
   └─ Logs: webhook_received, flow_project_id, flow_mr_iid

2. Validate and parse payload
   └─ Logs: Validation results

3. Background task: process_merge_request()
   └─ Logs: review_workflow_start

4. Fetch MR info from GitLab
   └─ Logs: fetch_mr_start, fetch_mr_complete

5. Fetch MR changes
   └─ Logs: fetch_mr_changes_start, fetch_mr_changes_complete

6. Clone repository
   └─ Logs: clone_start, clone_complete, size_mb

7. Initialize OpencodeReviewer
   └─ Logs: reviewer_init, has_rules

8. For each file:
   a. Load review rules from agent/rules/CODE_REVIEW.md
   b. Build prompt with rules
   c. Run opencode review
   └─ Logs: review_file_start, review_file_complete

9. Format and post review
   └─ Logs: post_mr_note_start, post_mr_note_complete

10. Cleanup
    └─ Logs: review_workflow_complete
```
## TO DO

* Gitlab baglantisi test edilmeli
* /review ve /ask komutlari eklenmeli. /review'de kullanicinin metni + diffler + codebase + review_system_prompt ele alinmali. /ask'te ise kullanicinin sordugu soru + diffler + codebase + explore_system_prompt ele alinmali
* parallelik getirilmeli ve max_concurennt job sayisi .env dosyasindan yonetilmeli
* Detailed code review ve general code review seçenekleri olmalı. Detailed code review diffin bulunduğu tüm kod dosyalarını ayrı ayrı review etmeli
* /review-in-detail komutu olmali sadece bunda tum doyalar ayri ayri taranmali. Ayri ayri tarama isini de paralel bir sekilde yapmali

## License

MIT License - Feel free to modify and distribute.

## Support

For issues or questions:
1. Check the logs in `logs/app.log`
2. Review this README
3. Test with the mock server first
4. Verify your `.env` configuration

## Acknowledgments

- [Opencode](https://opencode.ai) - The AI coding agent powering reviews
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [python-gitlab](https://python-gitlab.readthedocs.io/) - GitLab API client

"""
Configuration management for GitLab Opencode Reviewer.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class Config:
    """Application configuration."""
    
    # Server settings
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    webhook_secret: Optional[str] = field(default_factory=lambda: os.getenv("WEBHOOK_SECRET"))
    
    # GitLab settings
    gitlab_url: str = field(default_factory=lambda: os.getenv("GITLAB_URL", "https://gitlab.com"))
    gitlab_token: Optional[str] = field(default_factory=lambda: os.getenv("GITLAB_TOKEN"))
    
    # Opencode settings
    # Default to opencode/big-pickle which doesn't require external API keys
    opencode_model: str = field(default_factory=lambda: os.getenv(
        "OPENCODE_MODEL", 
        "opencode/big-pickle"
    ))
    opencode_timeout: int = field(default_factory=lambda: int(os.getenv("OPENCODE_TIMEOUT", "300")))
    
    # Review settings
    max_file_size_kb: int = field(default_factory=lambda: int(os.getenv("MAX_FILE_SIZE_KB", "500")))
    review_extensions: set = field(default_factory=lambda: set(
        os.getenv("REVIEW_EXTENSIONS", ".py,.js,.ts,.java,.go,.rs,.cpp,.c,.h,.rb,.php,.cs,.swift,.kt").split(",")
    ))
    skip_binary_files: bool = field(default_factory=lambda: os.getenv("SKIP_BINARY", "true").lower() == "true")
    
    # Paths
    temp_dir: Path = field(default_factory=lambda: Path(os.getenv("TEMP_DIR", "/tmp/gitlab-reviewer")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    
    # Simulation mode (for testing without GitLab)
    simulation_mode: bool = field(default_factory=lambda: os.getenv("SIMULATION_MODE", "false").lower() in ("true", "1", "yes", "on"))
    
    # Retry settings for agent tasks
    agent_task_max_retries: int = field(default_factory=lambda: int(os.getenv("AGENT_TASK_MAX_RETRIES", "2")))
    agent_task_retry_delay_seconds: int = field(default_factory=lambda: int(os.getenv("AGENT_TASK_RETRY_DELAY_SECONDS", "5")))
    agent_task_retry_backoff_multiplier: int = field(default_factory=lambda: int(os.getenv("AGENT_TASK_RETRY_BACKOFF_MULTIPLIER", "2")))
    agent_task_retry_on_timeout: bool = field(default_factory=lambda: os.getenv("AGENT_TASK_RETRY_ON_TIMEOUT", "true").lower() in ("true", "1", "yes", "on"))
    agent_task_retry_on_error: bool = field(default_factory=lambda: os.getenv("AGENT_TASK_RETRY_ON_ERROR", "true").lower() in ("true", "1", "yes", "on"))
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self.temp_dir = Path(self.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def is_gitlab_configured(self) -> bool:
        """Check if GitLab integration is properly configured."""
        return self.gitlab_token is not None
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of issues."""
        issues = []
        
        if not self.gitlab_token:
            issues.append("GITLAB_TOKEN not set (required for production)")
        
        if not self.opencode_model:
            issues.append("OPENCODE_MODEL not set")
        
        # Check if opencode is installed
        import shutil
        if not shutil.which("opencode"):
            issues.append("opencode CLI not found in PATH")
        
        return issues
    
    def to_dict(self) -> dict:
        """Convert config to dictionary (for logging)."""
        return {
            'host': self.host,
            'port': self.port,
            'gitlab_url': self.gitlab_url,
            'gitlab_configured': self.is_gitlab_configured,
            'simulation_mode': self.simulation_mode,
            'opencode_model': self.opencode_model,
            'opencode_timeout': self.opencode_timeout,
            'max_file_size_kb': self.max_file_size_kb,
            'temp_dir': str(self.temp_dir),
            'log_level': self.log_level,
            'agent_task_max_retries': self.agent_task_max_retries,
            'agent_task_retry_delay_seconds': self.agent_task_retry_delay_seconds,
            'agent_task_retry_on_timeout': self.agent_task_retry_on_timeout,
            'agent_task_retry_on_error': self.agent_task_retry_on_error,
        }


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config):
    """Set global configuration (useful for testing)."""
    global _config
    _config = config

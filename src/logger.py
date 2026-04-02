"""
Structured logging system for GitLab Opencode Reviewer.

Logs include: datetime, log_level, file_and_line, and contextual information.
"""

import logging
import sys
import os
from datetime import datetime
from typing import Any, Optional
from pathlib import Path
import json


class StructuredLogFormatter(logging.Formatter):
    """Custom formatter that outputs structured log data."""
    
    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()
        
        # Color codes
        self.colors = {
            'DEBUG': '\033[36m',      # Cyan
            'INFO': '\033[32m',       # Green
            'WARNING': '\033[33m',    # Yellow
            'ERROR': '\033[31m',      # Red
            'CRITICAL': '\033[35m',   # Magenta
            'RESET': '\033[0m',       # Reset
            'GRAY': '\033[90m',       # Gray for metadata
        }
    
    def format(self, record: logging.LogRecord) -> str:
        # Get current timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Get file and line information
        filename = os.path.basename(record.pathname)
        location = f"{filename}:{record.lineno}"
        
        # Get log level
        level = record.levelname
        
        # Build the main message
        message = record.getMessage()
        
        # Format extra fields if present
        extra_fields = {}
        standard_attrs = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
            'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
            'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
            'processName', 'process', 'getMessage', 'message'
        }
        
        for attr, value in record.__dict__.items():
            if attr not in standard_attrs and not attr.startswith('_'):
                extra_fields[attr] = value
        
        # Build extra info string
        extra_str = ""
        if extra_fields:
            extra_parts = [f"{k}={v}" for k, v in extra_fields.items()]
            extra_str = " | " + " ".join(extra_parts)
        
        if self.use_colors:
            color = self.colors.get(level, self.colors['RESET'])
            reset = self.colors['RESET']
            gray = self.colors['GRAY']
            
            formatted = (
                f"{gray}[{timestamp}]{reset} "
                f"{color}[{level:8}]{reset} "
                f"{gray}[{location:30}]{reset} "
                f"{message}{gray}{extra_str}{reset}"
            )
        else:
            formatted = f"[{timestamp}] [{level:8}] [{location:30}] {message}{extra_str}"
        
        # Add exception info if present
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            formatted += f"\n{exc_text}"
        
        return formatted


class JSONLogFormatter(logging.Formatter):
    """JSON formatter for machine-readable logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'file': os.path.basename(record.pathname),
            'line': record.lineno,
            'function': record.funcName,
            'message': record.getMessage(),
        }
        
        # Add extra fields
        standard_attrs = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
            'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
            'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
            'processName', 'process'
        }
        
        for attr, value in record.__dict__.items():
            if attr not in standard_attrs and not attr.startswith('_'):
                log_data[attr] = str(value)
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, default=str)


class LoggerManager:
    """Manages application logging configuration - single file output."""
    
    _instance: Optional['LoggerManager'] = None
    _initialized = False
    _shared_file_handler: Optional[logging.FileHandler] = None
    _shared_console_handler: Optional[logging.StreamHandler] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if LoggerManager._initialized:
            return
        
        self.log_dir = Path(__file__).parent.parent / "logs"
        self.log_dir.mkdir(exist_ok=True)
        self.loggers: dict[str, logging.Logger] = {}
        
        # Create single shared file handler for all loggers
        self.main_log_file = self.log_dir / "app.log"
        LoggerManager._shared_file_handler = logging.FileHandler(self.main_log_file)
        LoggerManager._shared_file_handler.setLevel(logging.DEBUG)
        LoggerManager._shared_file_handler.setFormatter(StructuredLogFormatter(use_colors=False))
        
        # Create single shared console handler
        LoggerManager._shared_console_handler = logging.StreamHandler(sys.stdout)
        LoggerManager._shared_console_handler.setLevel(logging.INFO)
        LoggerManager._shared_console_handler.setFormatter(StructuredLogFormatter(use_colors=True))
        
        LoggerManager._initialized = True
    
    def get_logger(self, name: str, log_file: Optional[str] = None) -> logging.Logger:
        """Get or create a logger with the given name."""
        
        if name in self.loggers:
            return self.loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        
        # Prevent propagation to avoid duplicate logs
        logger.propagate = False
        
        # Avoid adding handlers if they already exist
        if logger.handlers:
            self.loggers[name] = logger
            return logger
        
        # Add shared handlers (single file for all logs)
        logger.addHandler(LoggerManager._shared_file_handler)
        logger.addHandler(LoggerManager._shared_console_handler)
        
        self.loggers[name] = logger
        return logger
    
    def setup_root_logger(self):
        """Setup the root logger with basic configuration."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.WARNING)
        
        # Clear existing handlers
        root_logger.handlers = []
        
        # Add shared handlers
        if LoggerManager._shared_console_handler:
            root_logger.addHandler(LoggerManager._shared_console_handler)
        if LoggerManager._shared_file_handler:
            root_logger.addHandler(LoggerManager._shared_file_handler)


# Global logger manager instance
_logger_manager = LoggerManager()


def get_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        log_file: Optional specific log file name
        
    Returns:
        Configured logger instance
    """
    return _logger_manager.get_logger(name, log_file)


def log_flow_step(logger: logging.Logger, step: str, details: dict[str, Any]):
    """
    Log a flow step with structured details.
    
    Args:
        logger: Logger instance
        step: Name of the flow step
        details: Dictionary of details to log
    """
    extra = {'flow_step': step, **{f"flow_{k}": v for k, v in details.items()}}
    logger.info(f"FLOW: {step}", extra=extra)


# Convenience function for quick logging
def setup_logging():
    """Initialize logging system - all output goes to single app.log file."""
    _logger_manager.setup_root_logger()
    
    # Create main application logger (all logs go to same file)
    main_logger = get_logger("gitlab_reviewer")
    main_logger.info("Logging system initialized", extra={
        'log_file': str(_logger_manager.main_log_file),
        'log_levels': {'console': 'INFO', 'file': 'DEBUG'}
    })
    
    return main_logger

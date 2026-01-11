"""
Logging Setup Module - Comprehensive logging for Skills From Docs Pipeline

Provides:
- Category-based logging with runtime control
- File and console handlers
- Structured log format for analysis
- Performance tracking

Usage:
    from logging_setup import get_logger, LogCategory

    logger = get_logger()
    logger.info(f"{LogCategory.PARSER} Processing file: {path}")
"""

import os
import sys
import json
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Set
from dataclasses import dataclass
from functools import wraps
import time


# =============================================================================
# Log Categories
# =============================================================================

class LogCategory:
    """Standard log category tags for the pipeline."""

    # Core pipeline phases
    PARSER = "[SKILL_GEN][PARSER]"
    CONVERTER = "[SKILL_GEN][CONVERTER]"
    PIPELINE = "[SKILL_GEN][PIPELINE]"
    EXTRACTION = "[SKILL_GEN][EXTRACTION]"
    CLUSTERING = "[SKILL_GEN][CLUSTERING]"
    SYNTHESIS = "[SKILL_GEN][SYNTHESIS]"

    # Operations
    FILE_IO = "[SKILL_GEN][FILE_IO]"
    API_CALL = "[SKILL_GEN][API_CALL]"
    CONFIG = "[SKILL_GEN][CONFIG]"
    VALIDATION = "[SKILL_GEN][VALIDATION]"

    # Diagnostics
    PERF = "[SKILL_GEN][PERF]"
    DEBUG = "[SKILL_GEN][DEBUG]"
    ERROR = "[SKILL_GEN][ERROR]"


# =============================================================================
# Logging Configuration
# =============================================================================

@dataclass
class LoggingConfig:
    """Configuration for the logging system."""

    log_level: str = "INFO"
    log_file: Optional[Path] = None
    console_output: bool = True
    json_output: bool = False
    include_timestamp: bool = True
    max_file_size_mb: int = 10
    backup_count: int = 5
    enabled_categories: Set[str] = None
    disabled_categories: Set[str] = None

    def __post_init__(self):
        if self.enabled_categories is None:
            # All categories enabled by default
            self.enabled_categories = {
                "PARSER", "CONVERTER", "PIPELINE", "EXTRACTION",
                "CLUSTERING", "SYNTHESIS", "FILE_IO", "API_CALL",
                "CONFIG", "VALIDATION", "PERF", "ERROR"
            }
        if self.disabled_categories is None:
            # Only DEBUG disabled by default (too verbose)
            self.disabled_categories = {"DEBUG"}


_logging_config: Optional[LoggingConfig] = None
_logger: Optional[logging.Logger] = None


def load_logging_config(config_path: Optional[Path] = None) -> LoggingConfig:
    """
    Load logging configuration from file or use defaults.

    Args:
        config_path: Path to logging_config.json (optional)

    Returns:
        LoggingConfig instance
    """
    global _logging_config

    if _logging_config is not None:
        return _logging_config

    config = LoggingConfig()

    # Try to load from environment
    config.log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Try to load from file
    if config_path is None:
        # Check common locations
        possible_paths = [
            Path.cwd() / "logging_config.json",
            Path(__file__).parent.parent / "logging_config.json",
            Path.home() / ".claude" / "skills_logging.json",
        ]
        for p in possible_paths:
            if p.exists():
                config_path = p
                break

    if config_path and config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Apply loaded config
            config.log_level = data.get("global_settings", {}).get("log_level", config.log_level)
            config.include_timestamp = data.get("global_settings", {}).get("include_timestamp", True)

            # Process categories
            categories = data.get("log_categories", {})
            config.enabled_categories = {
                name for name, settings in categories.items()
                if settings.get("enabled", True)
            }
            config.disabled_categories = {
                name for name, settings in categories.items()
                if not settings.get("enabled", True)
            }
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load logging config from {config_path}: {e}", file=sys.stderr)

    _logging_config = config
    return config


# =============================================================================
# Category Filter
# =============================================================================

class CategoryFilter(logging.Filter):
    """Filter log records based on enabled/disabled categories."""

    CATEGORY_PATTERN = re.compile(r'\[SKILL_GEN\]\[([^\]]+)\]')

    def __init__(self, config: LoggingConfig):
        super().__init__()
        self.config = config

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log records based on category.

        Returns True if record should be logged, False to suppress.
        """
        msg = record.getMessage()

        # If no category tag, allow through
        if "[SKILL_GEN]" not in msg:
            return True

        # Extract category
        match = self.CATEGORY_PATTERN.search(msg)
        if not match:
            return True

        category = match.group(1).upper()

        # Check if explicitly disabled
        if category in self.config.disabled_categories:
            return False

        # Check if explicitly enabled (when using whitelist mode)
        if self.config.enabled_categories:
            return category in self.config.enabled_categories

        return True


# =============================================================================
# Custom Formatter
# =============================================================================

class SkillsLogFormatter(logging.Formatter):
    """Custom formatter with optional JSON output."""

    def __init__(self, json_output: bool = False, include_timestamp: bool = True):
        self.json_output = json_output
        self.include_timestamp = include_timestamp

        if include_timestamp:
            fmt = "%(asctime)s - %(levelname)s - %(message)s"
            datefmt = "%Y-%m-%d %H:%M:%S"
        else:
            fmt = "%(levelname)s - %(message)s"
            datefmt = None

        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        if self.json_output:
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
            }

            # Extract category if present
            match = CategoryFilter.CATEGORY_PATTERN.search(record.getMessage())
            if match:
                log_data["category"] = match.group(1)

            # Add exception info if present
            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)

            return json.dumps(log_data, ensure_ascii=False)

        return super().format(record)


# =============================================================================
# Logger Factory
# =============================================================================

def get_logger(name: str = "skills_gen", config: Optional[LoggingConfig] = None) -> logging.Logger:
    """
    Get or create the skills generation logger.

    Args:
        name: Logger name
        config: Optional LoggingConfig (uses defaults if not provided)

    Returns:
        Configured logger instance
    """
    global _logger

    if _logger is not None:
        return _logger

    if config is None:
        config = load_logging_config()

    logger = logging.getLogger(name)

    # Clear existing handlers
    logger.handlers.clear()

    # Set base level
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(logging.DEBUG)  # Capture all, filter at handler level

    # Create category filter
    category_filter = CategoryFilter(config)

    # Console handler
    if config.console_output:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(SkillsLogFormatter(
            json_output=False,
            include_timestamp=config.include_timestamp
        ))
        console_handler.addFilter(category_filter)
        logger.addHandler(console_handler)

    # File handler
    if config.log_file:
        try:
            config.log_file.parent.mkdir(parents=True, exist_ok=True)

            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                config.log_file,
                maxBytes=config.max_file_size_mb * 1024 * 1024,
                backupCount=config.backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)  # Log everything to file
            file_handler.setFormatter(SkillsLogFormatter(
                json_output=config.json_output,
                include_timestamp=True
            ))
            file_handler.addFilter(category_filter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file {config.log_file}: {e}", file=sys.stderr)

    _logger = logger
    return logger


def configure_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    console: bool = True,
    json_output: bool = False
) -> logging.Logger:
    """
    Configure logging with custom settings.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (optional)
        console: Enable console output
        json_output: Use JSON format for file logs

    Returns:
        Configured logger
    """
    global _logging_config, _logger

    # Reset if reconfiguring
    _logging_config = None
    _logger = None

    config = LoggingConfig(
        log_level=log_level,
        log_file=Path(log_file) if log_file else None,
        console_output=console,
        json_output=json_output
    )

    return get_logger(config=config)


# =============================================================================
# Utility Functions
# =============================================================================

def log_performance(operation: str):
    """
    Decorator to log function performance.

    Usage:
        @log_performance("Processing files")
        def process_files():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger()
            start_time = time.time()

            logger.debug(f"{LogCategory.PERF} Starting: {operation}")

            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.info(f"{LogCategory.PERF} Completed: {operation} ({elapsed:.2f}s)")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"{LogCategory.PERF} Failed: {operation} after {elapsed:.2f}s - {e}")
                raise

        return wrapper
    return decorator


def log_api_call(
    operation: str,
    model: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost: Optional[float] = None,
    success: bool = True
):
    """Log an API call with optional token/cost tracking."""
    logger = get_logger()

    parts = [f"{LogCategory.API_CALL} {operation}"]

    if model:
        parts.append(f"model={model}")
    if input_tokens is not None:
        parts.append(f"input_tokens={input_tokens}")
    if output_tokens is not None:
        parts.append(f"output_tokens={output_tokens}")
    if cost is not None:
        parts.append(f"cost=${cost:.4f}")

    message = " | ".join(parts)

    if success:
        logger.info(message)
    else:
        logger.error(message)


def log_file_operation(operation: str, path: Path, success: bool = True, details: str = ""):
    """Log a file I/O operation."""
    logger = get_logger()

    message = f"{LogCategory.FILE_IO} {operation}: {path}"
    if details:
        message += f" - {details}"

    if success:
        logger.debug(message)
    else:
        logger.error(message)


def log_validation(item: str, valid: bool, reason: str = ""):
    """Log a validation result."""
    logger = get_logger()

    status = "PASS" if valid else "FAIL"
    message = f"{LogCategory.VALIDATION} [{status}] {item}"
    if reason:
        message += f" - {reason}"

    if valid:
        logger.debug(message)
    else:
        logger.warning(message)


# =============================================================================
# Default Logging Config Template
# =============================================================================

DEFAULT_LOGGING_CONFIG = {
    "global_settings": {
        "log_level": "INFO",
        "include_timestamp": True
    },
    "log_categories": {
        "PARSER": {"enabled": True, "description": "Log parsing operations"},
        "CONVERTER": {"enabled": True, "description": "Log to SR-PTD conversion"},
        "PIPELINE": {"enabled": True, "description": "Pipeline orchestration"},
        "EXTRACTION": {"enabled": True, "description": "Phase B extraction"},
        "CLUSTERING": {"enabled": True, "description": "Phase C clustering"},
        "SYNTHESIS": {"enabled": True, "description": "Phase D synthesis"},
        "FILE_IO": {"enabled": False, "description": "File operations (verbose)"},
        "API_CALL": {"enabled": True, "description": "API calls with token tracking"},
        "CONFIG": {"enabled": True, "description": "Configuration loading"},
        "VALIDATION": {"enabled": True, "description": "Validation results"},
        "PERF": {"enabled": True, "description": "Performance metrics"},
        "DEBUG": {"enabled": False, "description": "Verbose debug output"},
        "ERROR": {"enabled": True, "description": "Error conditions"}
    }
}


def create_logging_config_template(path: Path):
    """Create a logging configuration template file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(DEFAULT_LOGGING_CONFIG, f, indent=2, ensure_ascii=False)
    print(f"Created logging config template: {path}")

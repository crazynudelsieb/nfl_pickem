"""
Logging configuration for NFL Pick'em application
Provides structured logging with different levels and formatters
"""

import logging
import logging.handlers
import os
from logging import Filter

from flask import current_app, has_request_context, request


class RequestContextFilter(Filter):
    """Add request context to log records"""

    def filter(self, record):
        if has_request_context():
            record.url = request.url
            record.remote_addr = request.remote_addr
            record.method = request.method
            record.user_agent = request.headers.get("User-Agent", "Unknown")
        else:
            record.url = "N/A"
            record.remote_addr = "N/A"
            record.method = "N/A"
            record.user_agent = "N/A"
        return True


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output"""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset_color = self.COLORS["RESET"]

        # Add color to the level name
        colored_levelname = f"{log_color}{record.levelname}{reset_color}"
        record.levelname = colored_levelname

        return super().format(record)


def setup_logging(app):
    """
    Setup comprehensive logging for the Flask application

    Args:
        app: Flask application instance
    """

    # Determine log level from config
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper())

    # Create logs directory if it doesn't exist
    log_dir = app.config.get("LOG_DIR", "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Configure root logger
    logging.basicConfig(level=log_level)
    root_logger = logging.getLogger()

    # Clear existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler with colors (for development)
    if app.config.get("LOG_TO_CONSOLE", True):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)

        if app.debug:
            console_formatter = ColoredFormatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s "
                "[%(filename)s:%(lineno)d]",
                datefmt="%H:%M:%S",
            )
        else:
            console_formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(RequestContextFilter())
        root_logger.addHandler(console_handler)

    # File handler for application logs
    if app.config.get("LOG_TO_FILE", True):
        app_log_file = os.path.join(log_dir, "nfl_pickem.log")
        file_handler = logging.handlers.RotatingFileHandler(
            app_log_file, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
        )
        file_handler.setLevel(log_level)

        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s "
            "[%(url)s] [%(remote_addr)s] [%(method)s] [%(user_agent)s]",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(RequestContextFilter())
        root_logger.addHandler(file_handler)

    # Error log file for errors and above
    error_log_file = os.path.join(log_dir, "errors.log")
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file, maxBytes=5 * 1024 * 1024, backupCount=3  # 5MB
    )
    error_handler.setLevel(logging.ERROR)

    error_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s "
        "[%(pathname)s:%(lineno)d] [%(url)s] [%(remote_addr)s]",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    error_handler.setFormatter(error_formatter)
    error_handler.addFilter(RequestContextFilter())
    root_logger.addHandler(error_handler)

    # Scheduler log file for background tasks
    scheduler_log_file = os.path.join(log_dir, "scheduler.log")
    scheduler_handler = logging.handlers.RotatingFileHandler(
        scheduler_log_file, maxBytes=5 * 1024 * 1024, backupCount=3  # 5MB
    )
    scheduler_handler.setLevel(logging.INFO)

    scheduler_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    scheduler_handler.setFormatter(scheduler_formatter)

    # Add scheduler handler only to scheduler-related loggers
    scheduler_logger = logging.getLogger("app.services.scheduler_service")
    scheduler_logger.addHandler(scheduler_handler)

    # Configure third-party loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("flask_limiter").setLevel(logging.WARNING)

    # Set APScheduler logging to WARNING to reduce verbosity (change to INFO for debugging)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    app.logger.info(f"Logging configured - Level: {logging.getLevelName(log_level)}")


def get_logger(name):
    """
    Get a logger instance with the specified name

    Args:
        name: Logger name (usually __name__)

    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)


def log_request_info():
    """Log request information for debugging"""
    if has_request_context():
        logger = get_logger(__name__)
        logger.debug(
            f"Request: {request.method} {request.url} "
            f"from {request.remote_addr} "
            f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}"
        )


def log_slow_query(query, duration):
    """
    Log slow database queries

    Args:
        query: SQL query string
        duration: Query execution time in seconds
    """
    if duration > current_app.config.get("SLOW_QUERY_THRESHOLD", 1.0):
        logger = get_logger("slow_queries")
        logger.warning(f"Slow query ({duration:.2f}s): {query}")


class ContextualLogger:
    """Logger that includes contextual information"""

    def __init__(self, name, context=None):
        self.logger = get_logger(name)
        self.context = context or {}

    def _format_message(self, message):
        if self.context:
            context_str = " ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{message} [{context_str}]"
        return message

    def debug(self, message, **kwargs):
        self.logger.debug(self._format_message(message), **kwargs)

    def info(self, message, **kwargs):
        self.logger.info(self._format_message(message), **kwargs)

    def warning(self, message, **kwargs):
        self.logger.warning(self._format_message(message), **kwargs)

    def error(self, message, **kwargs):
        self.logger.error(self._format_message(message), **kwargs)

    def critical(self, message, **kwargs):
        self.logger.critical(self._format_message(message), **kwargs)

    def exception(self, message, **kwargs):
        self.logger.exception(self._format_message(message), **kwargs)

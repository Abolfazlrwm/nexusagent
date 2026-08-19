"""Centralized logging setup for NexusAgent.

Provides get_logger() for obtaining namespaced loggers, and
configure_logging() to attach a single console handler with a
level derived from the existing Settings configuration.
"""

from __future__ import annotations

import logging

from nexusagent.config import Settings

_ROOT_LOGGER_NAME = "nexusagent"
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the nexusagent namespace.

    Without a name, returns the main "nexusagent" logger.
    With a name (e.g. "nexusagent.agent"), returns that named logger.
    """
    if name is None:
        return logging.getLogger(_ROOT_LOGGER_NAME)
    return logging.getLogger(name)


def _resolve_level(level: str) -> int:
    resolved = logging.getLevelName(level.upper())
    if not isinstance(resolved, int):
        raise ValueError(f"Invalid log level: {level!r}")  # noqa: TRY004
    return resolved


def configure_logging(level: str | None = None) -> logging.Logger:
    """Configure the nexusagent root logger with a console handler.

    The log level defaults to the value provided by Settings
    (NEXUS_LOG_LEVEL) unless explicitly overridden. Calling this
    function multiple times is safe and will not attach duplicate
    handlers.
    """
    if level is None:
        level = Settings.from_env().log_level

    resolved_level = _resolve_level(level)

    logger = logging.getLogger(_ROOT_LOGGER_NAME)
    logger.setLevel(resolved_level)
    logger.propagate = False

    has_console_handler = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    if not has_console_handler:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        logger.addHandler(handler)

    return logger

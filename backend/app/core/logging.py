"""Logging configuration for the application.

Logs go to stdout with a consistent, greppable format. Application
loggers live under the ``meddoc`` namespace and do not propagate to the
root logger, so framework noise stays separate.
"""

import logging
import sys

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_LOGGER_NAME = "meddoc"


def setup_logging(level: str = "INFO") -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger, e.g. get_logger("rag") -> meddoc.rag."""
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
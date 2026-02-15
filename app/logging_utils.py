"""Central logging configuration used across modules."""

from __future__ import annotations

import logging


def setup_logger(log_level: str = "INFO", log_file: str | None = None) -> logging.Logger:
    """Configure and return the app logger.

    Logs are written to console, plus an optional file if `log_file` is set.
    """
    logger = logging.getLogger("algotrade")
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


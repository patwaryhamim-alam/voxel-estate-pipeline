"""
Central logging utility for the pipeline.

DESIGN PRINCIPLE:
    Every module imports from here. One place to control where logs go.
    Swapping to a cloud logger (Sentry, Logtail) later = only edit this file.

USAGE:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Starting pipeline")
    log.error("Something failed", exc_info=True)
"""

import os
import logging
from datetime import datetime
from pathlib import Path


# Ensure logs/ folder exists
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger that writes to:
        - logs/run_YYYY-MM-DD.log   (all activity)
        - logs/errors_YYYY-MM-DD.log (only errors)
        - Console (for real-time visibility)

    Args:
        name: Usually __name__ of the calling module

    Returns:
        Configured logging.Logger instance
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    today = datetime.now().strftime("%Y-%m-%d")
    run_log = LOG_DIR / f"run_{today}.log"
    err_log = LOG_DIR / f"errors_{today}.log"

    # Format: time | level | module | message
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler 1: Full run log
    fh_all = logging.FileHandler(run_log, encoding="utf-8")
    fh_all.setLevel(logging.INFO)
    fh_all.setFormatter(fmt)
    logger.addHandler(fh_all)

    # Handler 2: Errors-only log
    fh_err = logging.FileHandler(err_log, encoding="utf-8")
    fh_err.setLevel(logging.ERROR)
    fh_err.setFormatter(fmt)
    logger.addHandler(fh_err)

    # Handler 3: Console (so you see it live)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger
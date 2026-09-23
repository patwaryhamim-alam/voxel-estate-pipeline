"""
Central logging utility for the pipeline.

DESIGN PRINCIPLE:
    Every module imports from here. One place to control where logs go.

FIX 6 (updated):
    Local file logs keep FULL tracebacks (gitignored, safe for debug).
    Console output uses TRIMMED tracebacks (readable).
    Admin emails still use TRIMMED (alerts.py).

    This gives:
      - logs/run_*.log       → full traceback (debugging)
      - logs/errors_*.log    → full traceback (debugging)
      - Console              → trimmed (readable)
      - Admin email          → trimmed (alerts.py, unchanged)

USAGE:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Starting pipeline")
    log.error("Something failed", exc_info=True)
"""

import os
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

RETENTION_DAYS = 30
MAX_TRACEBACK_FRAMES = 5  # For console only


# ============================================================
# FULL FORMATTER — for file logs (untrimmed tracebacks)
# ============================================================
class _FullFormatter(logging.Formatter):
    """
    Standard formatter. Full exception traceback included as-is.

    Used for:
        - logs/run_*.log     (all activity)
        - logs/errors_*.log  (errors only)

    These files are gitignored — no privacy risk. Full trace is
    essential for debugging production issues.
    """
    pass  # Uses logging.Formatter.formatException() — full by default


# ============================================================
# TRIMMED FORMATTER — for console (readable)
# ============================================================
class _TrimmedFormatter(logging.Formatter):
    """
    Trims exception tracebacks to first N/2 + last N/2 frames.

    Used for:
        - Console (StreamHandler)

    Keeps output readable — no 30-line pandas stack on screen.
    """

    def formatException(self, ei) -> str:
        import traceback

        exc_type, exc_value, exc_tb = ei
        frames = traceback.extract_tb(exc_tb)
        total = len(frames)

        if total <= MAX_TRACEBACK_FRAMES:
            return super().formatException(ei)

        head_n = MAX_TRACEBACK_FRAMES // 2
        tail_n = MAX_TRACEBACK_FRAMES - head_n
        kept = frames[:head_n] + frames[-tail_n:]
        trimmed_tb = "".join(traceback.format_list(kept))

        omitted = total - MAX_TRACEBACK_FRAMES
        note = f"\n    [... {omitted} intermediate frames omitted — see logs/ for full trace ...]\n"

        exc_line = "".join(
            traceback.format_exception_only(exc_type, exc_value)
        )

        return (
            f"Traceback (trimmed, {total} total frames — "
            f"full trace in logs/):\n{trimmed_tb}{note}{exc_line}"
        )


# ============================================================
# LOG ROTATION
# ============================================================
def _rotate_old_logs():
    """Delete log files older than RETENTION_DAYS."""
    try:
        cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
        deleted = 0

        for pattern in ("run_*.log", "errors_*.log"):
            for log_file in LOG_DIR.glob(pattern):
                try:
                    match = re.search(r"(\d{4}-\d{2}-\d{2})", log_file.name)
                    if not match:
                        continue
                    file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
                    if file_date < cutoff:
                        log_file.unlink()
                        deleted += 1
                except (ValueError, OSError):
                    continue

        return deleted
    except Exception:
        return 0


_rotation_done = False


# ============================================================
# PUBLIC: get_logger()
# ============================================================
def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger that writes to:
        - logs/run_YYYY-MM-DD.log    (all activity, FULL traceback)
        - logs/errors_YYYY-MM-DD.log (errors only, FULL traceback)
        - Console                    (trimmed traceback)
    """
    global _rotation_done

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    if not _rotation_done:
        _rotate_old_logs()
        _rotation_done = True

    today = datetime.now().strftime("%Y-%m-%d")
    run_log = LOG_DIR / f"run_{today}.log"
    err_log = LOG_DIR / f"errors_{today}.log"

    # Fix 6: separate formatters — file (full) vs console (trimmed)
    full_fmt = _FullFormatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    trimmed_fmt = _TrimmedFormatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler 1: Full run log (FULL traceback)
    fh_all = logging.FileHandler(run_log, encoding="utf-8")
    fh_all.setLevel(logging.INFO)
    fh_all.setFormatter(full_fmt)
    logger.addHandler(fh_all)

    # Handler 2: Errors-only log (FULL traceback)
    fh_err = logging.FileHandler(err_log, encoding="utf-8")
    fh_err.setLevel(logging.ERROR)
    fh_err.setFormatter(full_fmt)
    logger.addHandler(fh_err)

    # Handler 3: Console (TRIMMED traceback)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(trimmed_fmt)
    logger.addHandler(ch)

    return logger


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("LOGGER TEST v2 — Full trace in files, trimmed on console")
    print("=" * 60)

    log = get_logger(__name__)

    log.info("Test info message")
    log.warning("Test warning message")

    print("\n[1] Deep exception (console should show trimmed, "
          "file should have full):")
    try:
        def level_5(): return 1 / 0
        def level_4(): return level_5()
        def level_3(): return level_4()
        def level_2(): return level_3()
        def level_1(): return level_2()
        level_1()
    except Exception:
        log.error("Deep exception test", exc_info=True)

    print("\n[2] Rotation check...")
    deleted = _rotate_old_logs()
    print(f"   Deleted {deleted} old log file(s) (>{RETENTION_DAYS} days)")

    print("\n[3] Verify formatter types:")
    logger = get_logger(__name__)
    for i, h in enumerate(logger.handlers):
        fmt = type(h.formatter).__name__
        target = "FILE" if isinstance(h, logging.FileHandler) else "CONSOLE"
        print(f"   Handler {i}: {target} → {fmt}")

    print("\n✅ Logger test complete")
    print("   Check logs/run_*.log — should have FULL traceback")
    print("   Console output above — should be TRIMMED")
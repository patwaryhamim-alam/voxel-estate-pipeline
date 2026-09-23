"""
FILE WATCHER — Inbox Scanner
=============================
Scans inbox/<client_id>/ for new CSV files.
Moves them to processed/<client_id>/ ONLY after FULL processing.

PARTIAL-RUN BEHAVIOR (Fix 1):
    If a file is only partially processed (e.g., quota exhausted
    mid-way), it STAYS in inbox/. Next run re-processes it:
      - Classified leads → cache hit (0 API calls)
      - Unclassified leads → API call
      - Sheet duplicate check skips already-pushed rows
      - File moves to processed/ only when ALL leads are classified

DESIGN:
    - Each client has own inbox folder
    - Processed files moved (not deleted) for audit trail
    - Handles multiple CSVs per client
    - Content hash used to detect duplicate uploads of FULLY processed files
    - Inbox file presence = "still needs processing" (implicit state)

USAGE:
    from file_watcher import scan_inbox, move_to_processed
    from file_watcher import is_already_processed, has_inbox_files
    
    files = scan_inbox("client_001")
    for file_path in files:
        fully_done = process(file_path)
        if fully_done:
            move_to_processed("client_001", file_path)
        # else: leave in inbox for next run
"""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Import logger if available
try:
    from logger import get_logger
    log = get_logger(__name__)
except ImportError:
    import logging
    log = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent
INBOX_DIR = PROJECT_ROOT / "inbox"
PROCESSED_DIR = PROJECT_ROOT / "processed"

SUPPORTED_EXTENSIONS = [".csv", ".xlsx", ".xls"]


# ============================================================
# HELPERS
# ============================================================
def _get_client_inbox(client_id: str) -> Path:
    """Get inbox folder path for a client."""
    return INBOX_DIR / client_id


def _get_client_processed(client_id: str) -> Path:
    """Get processed folder path for a client."""
    return PROCESSED_DIR / client_id


def get_file_hash(file_path: Path) -> str:
    """
    Calculate SHA256 hash of a file (public helper).

    Used by:
        - is_already_processed() to detect duplicate uploads
        - Future: state tracking in partial runs
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# Backward-compat alias
_file_hash = get_file_hash


# ============================================================
# PUBLIC: scan_inbox()
# ============================================================
def scan_inbox(client_id: str) -> List[Path]:
    """
    Scan inbox/<client_id>/ for supported files.

    Fix 1: Files stay in inbox until FULLY processed.
    A partial file will be returned here again on the next run.

    Args:
        client_id: e.g., "client_001"

    Returns:
        List of Path objects (files ready to process), sorted by name
    """
    inbox = _get_client_inbox(client_id)

    if not inbox.exists():
        log.warning(f"Inbox folder does not exist: {inbox}")
        return []

    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(inbox.glob(f"*{ext}"))

    # Filter out temp files (Excel ~, hidden .)
    files = [f for f in files
             if not f.name.startswith("~") and not f.name.startswith(".")]
    files = sorted(files)

    if files:
        log.info(f"Found {len(files)} file(s) in inbox/{client_id}")
    else:
        log.info(f"No new files in inbox/{client_id}")

    return files


# ============================================================
# PUBLIC: has_inbox_files()
# ============================================================
def has_inbox_files(client_id: str) -> bool:
    """
    Quick check: are there files waiting in inbox?

    Fix 1 helper — useful for run summary and health checks.
    """
    return len(scan_inbox(client_id)) > 0


# ============================================================
# PUBLIC: move_to_processed()
# ============================================================
def move_to_processed(client_id: str, file_path: Path) -> Path:
    """
    Move a file from inbox/ to processed/ after FULL processing.

    Fix 1: ONLY call this when ALL leads in the file are classified.
    If any lead is pending, the file must STAY in inbox for retry.

    Args:
        client_id: e.g., "client_001"
        file_path: Path to file in inbox

    Returns:
        New Path in processed folder
    """
    file_path = Path(file_path)
    processed = _get_client_processed(client_id)
    processed.mkdir(parents=True, exist_ok=True)

    # Timestamp prefix prevents overwrite if same filename uploaded twice
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = file_path.stem
    suffix = file_path.suffix
    new_name = f"{timestamp}_{stem}{suffix}"
    new_path = processed / new_name

    shutil.move(str(file_path), str(new_path))
    log.info(f"Moved {file_path.name} → processed/{client_id}/{new_name}")
    print(f"[FileWatcher] Moved to processed: {new_name}")

    return new_path


# ============================================================
# PUBLIC: get_next_csv_for_client()
# ============================================================
def get_next_csv_for_client(client_id: str) -> Optional[Path]:
    """
    Get the next CSV file to process for a client.

    Returns:
        Path to the oldest file, or None if inbox is empty
    """
    files = scan_inbox(client_id)
    return files[0] if files else None


# ============================================================
# PUBLIC: is_already_processed()
# ============================================================
def is_already_processed(client_id: str, file_path: Path) -> bool:
    """
    Check if a file (by content hash) was already FULLY processed.

    Fix 1: Only checks the processed/ folder. A partially-processed
    file stays in inbox/ and will NOT match here, so it will be
    re-processed on the next run (correct behavior).

    Useful for detecting duplicate uploads of fully-processed files.

    Args:
        client_id: e.g., "client_001"
        file_path: Path to file to check

    Returns:
        True if a file with the same hash exists in processed/
    """
    file_hash = get_file_hash(file_path)
    processed = _get_client_processed(client_id)

    if not processed.exists():
        return False

    for old_file in processed.glob("*"):
        try:
            if get_file_hash(old_file) == file_hash:
                log.warning(f"File already processed: {old_file.name}")
                return True
        except Exception:
            continue

    return False


# ============================================================
# PUBLIC: get_inbox_stats()
# ============================================================
def get_inbox_stats(client_id: str) -> dict:
    """
    Return stats about inbox for a client.

    Fix 1 helper — useful for run summary and admin dashboard.
    """
    files = scan_inbox(client_id)
    total_size = 0
    for f in files:
        try:
            total_size += f.stat().st_size
        except OSError:
            pass

    return {
        "client_id": client_id,
        "files_waiting": len(files),
        "total_bytes": total_size,
        "filenames": [f.name for f in files],
    }


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("FILE WATCHER TEST — Fix 1 (Partial-Run Aware)")
    print("=" * 60)

    client = "client_001"
    print(f"\n[1] Scanning inbox/{client}/...")

    files = scan_inbox(client)

    if not files:
        print(f"   No files found in inbox/{client}/")
        print(f"   To test: place a CSV at inbox/{client}/leads.csv")
    else:
        print(f"   Found {len(files)} file(s):")
        for f in files:
            print(f"     - {f.name} ({f.stat().st_size} bytes)")

    # Test stats helper
    print(f"\n[2] Inbox stats:")
    stats = get_inbox_stats(client)
    for k, v in stats.items():
        if k == "filenames":
            print(f"   {k}: {v[:3]}{'...' if len(v) > 3 else ''}")
        else:
            print(f"   {k}: {v}")

    # Test has_inbox_files
    print(f"\n[3] has_inbox_files: {has_inbox_files(client)}")

    print("\n✅ File watcher test complete")
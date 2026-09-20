"""
FILE WATCHER — Inbox Scanner
=============================
Scans inbox/<client_id>/ for new CSV files.
Moves them to processed/<client_id>/ after processing.

USAGE:
    from file_watcher import scan_inbox, move_to_processed
    
    files = scan_inbox("client_001")
    for file_path in files:
        process(file_path)
        move_to_processed("client_001", file_path)

DESIGN:
    - Each client has own inbox folder
    - Processed files moved (not deleted) for audit trail
    - Handles multiple CSVs per client
    - Warns if file already processed (checksum match)
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


def _file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file (for dedup)."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# ============================================================
# PUBLIC: scan_inbox()
# ============================================================
def scan_inbox(client_id: str) -> List[Path]:
    """
    Scan inbox/<client_id>/ for supported files.

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

    # Filter out temp files
    files = [f for f in files if not f.name.startswith("~") and not f.name.startswith(".")]
    files = sorted(files)

    if files:
        log.info(f"Found {len(files)} file(s) in inbox/{client_id}")
    else:
        log.info(f"No new files in inbox/{client_id}")

    return files


# ============================================================
# PUBLIC: move_to_processed()
# ============================================================
def move_to_processed(client_id: str, file_path: Path) -> Path:
    """
    Move a file from inbox/ to processed/ after processing.

    Args:
        client_id: e.g., "client_001"
        file_path: Path to file in inbox

    Returns:
        New Path in processed folder
    """
    file_path = Path(file_path)
    processed = _get_client_processed(client_id)
    processed.mkdir(parents=True, exist_ok=True)

    # Add timestamp to avoid overwrite if same filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = file_path.stem
    suffix = file_path.suffix
    new_name = f"{timestamp}_{stem}{suffix}"
    new_path = processed / new_name

    shutil.move(str(file_path), str(new_path))
    log.info(f"Moved {file_path.name} → processed/{client_id}/{new_name}")

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
    Check if a file (by content hash) was already processed.

    Useful for detecting duplicate uploads.
    """
    file_hash = _file_hash(file_path)
    processed = _get_client_processed(client_id)

    if not processed.exists():
        return False

    for old_file in processed.glob("*"):
        try:
            if _file_hash(old_file) == file_hash:
                log.warning(f"File already processed: {old_file.name}")
                return True
        except Exception:
            continue

    return False


# ============================================================
# TEST — run this file directly
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("FILE WATCHER TEST")
    print("=" * 60)

    # Check client_001
    client = "client_001"
    print(f"\nScanning inbox/{client}/...")

    files = scan_inbox(client)

    if not files:
        print(f"  No files found in inbox/{client}/")
        print(f"  To test: place a CSV at inbox/{client}/leads.csv")
    else:
        print(f"  Found {len(files)} file(s):")
        for f in files:
            print(f"    - {f.name} ({f.stat().st_size} bytes)")
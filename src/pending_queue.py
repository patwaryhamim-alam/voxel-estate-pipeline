"""
PENDING QUEUE
=============
Tracks leads that couldn't be classified due to AI quota exhaustion.
They are retried on the next pipeline run.

DESIGN:
    - Save pending leads to pending/pending_YYYYMMDD_HHMMSS.json
    - Each file = one batch of unprocessed leads
    - load_pending() reads ALL pending files, sorted by PRIORITY
    - clear_pending() deletes files after successful processing
    - No silent fallback — pending leads are NEVER pushed to sheet

PRIORITY SORT (Fix 4):
    Pending leads are reordered so the most valuable leads
    (distress signals, out-of-state absentee, large price drops)
    are retried FIRST when the next run has limited quota.

USAGE:
    from pending_queue import save_pending, load_pending, clear_pending, pending_count
    
    save_pending(leads, reason="quota")
    pending = load_pending()  # List of dicts, priority-sorted
    clear_pending()  # After successful run
    print(pending_count())
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

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
PENDING_DIR = PROJECT_ROOT / "pending"


# ============================================================
# INTERNAL: Ensure directory exists
# ============================================================
def _ensure_dir():
    PENDING_DIR.mkdir(exist_ok=True)


# ============================================================
# INTERNAL: Priority scoring
# ============================================================
def _priority_score(lead: Dict[str, Any]) -> float:
    """
    Compute priority score for a pending lead. Higher = retry first.

    Priority rules:
      - Distress signals present    → +100
      - Out-of-state absentee       → +50
      - In-state absentee           → +25
      - Price drop magnitude        → +drop (tiebreaker)

    LLC/Trust is intentionally NOT scored (informational only).
    """
    try:
        distress = (lead.get("distress_signals") or "").lower()
        owner = (lead.get("owner_status") or "").lower()
        drop = float(lead.get("price_drop_pct") or 0)
    except (ValueError, TypeError):
        return 0.0

    score = 0.0

    # Distress signals
    if distress and distress != "none":
        score += 100

    # Owner status
    if "out_of_state_absentee" in owner:
        score += 50
    elif "in_state_absentee" in owner:
        score += 25

    # Price drop as tiebreaker
    score += round(drop, 1)

    return score


# ============================================================
# PUBLIC: save_pending()
# ============================================================
def save_pending(leads: List[Dict[str, Any]], reason: str = "unknown") -> str:
    """
    Save a batch of pending leads to a JSON file.

    Args:
        leads: List of lead dicts (PII-free payload from llm_provider)
        reason: Why these are pending (e.g., "quota", "api_error")

    Returns:
        Path to saved file (as string), or "" on failure
    """
    if not leads:
        return ""

    _ensure_dir()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Add microseconds to avoid filename collision when saving fast
    micros = datetime.now().strftime("%f")[:4]
    filename = f"pending_{timestamp}_{micros}.json"
    filepath = PENDING_DIR / filename

    payload = {
        "created_at": datetime.now().isoformat(),
        "reason": reason,
        "lead_count": len(leads),
        "leads": leads,
    }

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        log.warning(f"Saved {len(leads)} pending leads to {filename} "
                    f"(reason: {reason})")
        print(f"[Pending] Saved {len(leads)} leads to {filename} "
              f"(will retry next run)")
        return str(filepath)
    except Exception as e:
        log.error(f"Failed to save pending: {e}")
        return ""


# ============================================================
# PUBLIC: load_pending()
# ============================================================
def load_pending() -> List[Dict[str, Any]]:
    """
    Load ALL pending leads from all pending files, sorted by priority.

    Priority order:
      1. Distress signals present
      2. Out-of-state absentee
      3. In-state absentee
      4. Larger price drop

    Returns:
        Combined list of lead dicts (highest priority first)
    """
    if not PENDING_DIR.exists():
        return []

    all_leads = []
    files = sorted(PENDING_DIR.glob("pending_*.json"))  # FIFO by filename

    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            leads = data.get("leads", [])
            all_leads.extend(leads)
            log.info(f"Loaded {len(leads)} leads from {filepath.name}")
        except Exception as e:
            log.warning(f"Could not read {filepath.name}: {e}")

    if all_leads:
        # Sort by priority descending (highest first)
        all_leads.sort(key=_priority_score, reverse=True)
        print(f"[Pending] Loaded {len(all_leads)} pending leads from "
              f"{len(files)} file(s) — priority-sorted")
        log.info(f"Total pending leads loaded: {len(all_leads)} "
                 f"(priority-sorted, top score="
                 f"{_priority_score(all_leads[0]):.1f})")

    return all_leads


# ============================================================
# PUBLIC: clear_pending()
# ============================================================
def clear_pending() -> int:
    """
    Delete all pending files (call after successful run).

    Returns:
        Number of files deleted
    """
    if not PENDING_DIR.exists():
        return 0

    files = list(PENDING_DIR.glob("pending_*.json"))
    count = 0

    for filepath in files:
        try:
            filepath.unlink()
            count += 1
        except Exception as e:
            log.warning(f"Could not delete {filepath.name}: {e}")

    if count > 0:
        log.info(f"Cleared {count} pending file(s)")
        print(f"[Pending] Cleared {count} file(s)")

    return count


# ============================================================
# PUBLIC: pending_count()
# ============================================================
def pending_count() -> int:
    """Return total count of pending leads across all files."""
    if not PENDING_DIR.exists():
        return 0

    total = 0
    for filepath in PENDING_DIR.glob("pending_*.json"):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            total += data.get("lead_count", 0)
        except Exception:
            continue

    return total


# ============================================================
# PUBLIC: has_pending()
# ============================================================
def has_pending() -> bool:
    """Quick check if any pending leads exist."""
    return pending_count() > 0


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("PENDING QUEUE TEST v2 — Priority Sort")
    print("=" * 60)

    # Cleanup first
    clear_pending()

    # Test 1: Empty state
    print(f"\n[1] Initial state:")
    print(f"   pending_count: {pending_count()}")
    print(f"   has_pending: {has_pending()}")

    # Test 2: Save pending — mixed priority
    print(f"\n[2] Saving 5 test leads (mixed priority)...")
    test_leads = [
        {"lead_id": 0, "listing_type": "FSBO", "price_drop_pct": 2.0,
         "county": "Dallas", "owner_status": "owner_occupied",
         "distress_signals": ""},
        {"lead_id": 1, "listing_type": "FSBO", "price_drop_pct": 5.0,
         "county": "Dallas", "owner_status": "owner_occupied",
         "distress_signals": "tax_delinquent"},
        {"lead_id": 2, "listing_type": "price_drop", "price_drop_pct": 8.0,
         "county": "Travis", "owner_status": "out_of_state_absentee",
         "distress_signals": ""},
        {"lead_id": 3, "listing_type": "price_drop", "price_drop_pct": 0.0,
         "county": "Travis", "owner_status": "owner_occupied",
         "distress_signals": ""},
        {"lead_id": 4, "listing_type": "FSBO", "price_drop_pct": 3.0,
         "county": "Dallas", "owner_status": "in_state_absentee",
         "distress_signals": ""},
    ]
    save_pending(test_leads, reason="quota")

    # Test 3: Verify
    print(f"\n[3] After save:")
    print(f"   pending_count: {pending_count()}")
    print(f"   has_pending: {has_pending()}")

    # Test 4: Load — should be priority-sorted
    print(f"\n[4] Loading pending (priority-sorted)...")
    loaded = load_pending()
    print(f"   Loaded {len(loaded)} leads")
    print(f"   Priority order (lead_id, score):")
    for l in loaded:
        print(f"      lead_id={l['lead_id']}, "
              f"score={_priority_score(l):.1f}, "
              f"distress='{l.get('distress_signals','')}', "
              f"owner='{l.get('owner_status','')}'")

    scores = [_priority_score(l) for l in loaded]
    is_sorted = all(scores[i] >= scores[i+1] for i in range(len(scores)-1))
    print(f"   {'OK ' if is_sorted else 'FAIL'} Priority sort correct")
    print(f"   Expected first lead_id=1 (distress) — "
          f"got {loaded[0]['lead_id']}")
    print(f"   Expected last  lead_id=3 (no signal) — "
          f"got {loaded[-1]['lead_id']}")

    # Test 5: Save another batch
    print(f"\n[5] Saving another batch (3 leads)...")
    save_pending(test_leads[:3], reason="api_error")
    print(f"   pending_count now: {pending_count()}")

    # Test 6: Clear
    print(f"\n[6] Clearing all pending...")
    cleared = clear_pending()
    print(f"   Cleared {cleared} file(s)")
    print(f"   pending_count now: {pending_count()}")

    print("\n✅ Test complete")
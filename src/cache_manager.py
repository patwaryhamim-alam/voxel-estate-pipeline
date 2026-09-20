"""
CLASSIFICATION CACHE (SQLite) — v2
==================================
Caches AI classification results to avoid re-classifying same leads.

v2 FIX (CRITICAL):
    - Old key: listing_type + price_drop_pct + owner_status + county
      → Different leads with same values collided, causing WRONG cached results

    - New key: hash(ALL classification features + prompt version + model name)
      → Every unique lead gets unique key
      → Prompt changes auto-invalidate cache
      → Model changes auto-invalidate cache

DESIGN:
    - Hash uses ALL fields sent to AI (except internal lead_id)
    - Prompt version constant is included in hash
    - Model name is included in hash
    - Change prompt → bump PROMPT_VERSION → cache auto-clears
    - Change model → cache auto-clears

USAGE:
    from cache_manager import get_many, save_many, cache_stats
"""

import os
import json
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

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
CACHE_DIR = PROJECT_ROOT / "cache"
DB_PATH = CACHE_DIR / "classifications.db"

# ⚠️ BUMP THIS when prompt rules change in llm_provider.py
# Format: v1, v2, v3, ... (integer increase)
PROMPT_VERSION = "v1"

# Model name from env (defaults to gemini-3.5-flash)
MODEL_NAME = os.getenv("LLM_MODEL", "gemini-3.5-flash")

# Fields EXCLUDED from hash (internal metadata)
EXCLUDE_FROM_HASH = {"lead_id"}


# ============================================================
# SETUP
# ============================================================
def _ensure_db():
    """Create cache folder and DB table if missing."""
    CACHE_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS classifications (
                lead_hash TEXT PRIMARY KEY,
                signal_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                hit_count INTEGER DEFAULT 0
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ============================================================
# HASHING (v2 — full payload + version)
# ============================================================
def _lead_hash(lead: Dict[str, Any]) -> str:
    """
    Create stable hash from ALL classification-relevant fields.

    Includes:
        - Every field in the lead dict (except excluded internal fields)
        - PROMPT_VERSION (bump to invalidate cache)
        - MODEL_NAME (auto-invalidates when model changes)

    Excludes:
        - lead_id (internal reference only)
    """
    # Copy dict, remove internal-only fields
    hash_input = {
        k: v for k, v in lead.items()
        if k not in EXCLUDE_FROM_HASH
    }

    # Add version context — changes invalidate cache
    hash_input["_prompt_version"] = PROMPT_VERSION
    hash_input["_model_name"] = MODEL_NAME

    # Stable serialization (sorted keys = deterministic)
    serialized = json.dumps(hash_input, sort_keys=True, default=str)

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ============================================================
# PUBLIC: get_cached()
# ============================================================
def get_cached(lead: Dict[str, Any]) -> Optional[Dict]:
    """Get cached classification for a lead."""
    try:
        _ensure_db()
        h = _lead_hash(lead)

        conn = sqlite3.connect(str(DB_PATH))
        try:
            cursor = conn.execute(
                "SELECT signal_type, reason FROM classifications WHERE lead_hash = ?",
                (h,)
            )
            row = cursor.fetchone()

            if row:
                conn.execute(
                    "UPDATE classifications SET hit_count = hit_count + 1 "
                    "WHERE lead_hash = ?",
                    (h,)
                )
                conn.commit()
                return {"signal_type": row[0], "reason": row[1]}
            return None
        finally:
            conn.close()
    except Exception as e:
        log.warning(f"Cache read error: {e}")
        return None


# ============================================================
# PUBLIC: save_result()
# ============================================================
def save_result(lead: Dict[str, Any], signal_type: str, reason: str) -> bool:
    """Save classification result to cache."""
    try:
        _ensure_db()
        h = _lead_hash(lead)

        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO classifications
                (lead_hash, signal_type, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (h, signal_type, reason, datetime.now().isoformat())
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        log.warning(f"Cache write error: {e}")
        return False


# ============================================================
# PUBLIC: get_many() — batch cache lookup
# ============================================================
def get_many(leads: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
    """
    Batch cache lookup.

    Returns:
        (cached_results, uncached_leads)
    """
    if not leads:
        return [], []

    _ensure_db()
    cached_results = []
    uncached_leads = []

    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            for lead in leads:
                h = _lead_hash(lead)
                cursor = conn.execute(
                    "SELECT signal_type, reason FROM classifications WHERE lead_hash = ?",
                    (h,)
                )
                row = cursor.fetchone()

                if row:
                    cached_results.append({
                        "lead_id": lead["lead_id"],
                        "signal_type": row[0],
                        "reason": row[1],
                        "from_cache": True,
                    })
                    conn.execute(
                        "UPDATE classifications SET hit_count = hit_count + 1 "
                        "WHERE lead_hash = ?",
                        (h,)
                    )
                else:
                    uncached_leads.append(lead)

            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        log.warning(f"Cache batch read error: {e}")
        return [], leads

    log.info(f"Cache: {len(cached_results)} hits, {len(uncached_leads)} misses")
    return cached_results, uncached_leads


# ============================================================
# PUBLIC: save_many() — batch cache write
# ============================================================
def save_many(results: List[Dict[str, Any]],
              original_leads: List[Dict[str, Any]]) -> int:
    """Save multiple results at once."""
    if not results or not original_leads:
        return 0

    _ensure_db()

    # Map lead_id → original lead
    lead_map = {lead["lead_id"]: lead for lead in original_leads}
    saved = 0

    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            for r in results:
                lead = lead_map.get(r["lead_id"])
                if not lead:
                    continue

                h = _lead_hash(lead)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO classifications
                    (lead_hash, signal_type, reason, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (h, r["signal_type"], r.get("reason", ""),
                     datetime.now().isoformat())
                )
                saved += 1

            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        log.warning(f"Cache batch write error: {e}")

    return saved


# ============================================================
# PUBLIC: cache_stats()
# ============================================================
def cache_stats() -> Dict[str, Any]:
    """Return cache statistics."""
    try:
        _ensure_db()
        conn = sqlite3.connect(str(DB_PATH))
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM classifications")
            total = cursor.fetchone()[0]

            cursor = conn.execute("SELECT SUM(hit_count) FROM classifications")
            total_hits = cursor.fetchone()[0] or 0

            return {
                "total_cached": total,
                "total_hits": total_hits,
                "db_size_kb": round(DB_PATH.stat().st_size / 1024, 1)
                              if DB_PATH.exists() else 0,
                "prompt_version": PROMPT_VERSION,
                "model_name": MODEL_NAME,
            }
        finally:
            conn.close()
    except Exception as e:
        log.warning(f"Cache stats error: {e}")
        return {"total_cached": 0, "total_hits": 0, "db_size_kb": 0}


# ============================================================
# PUBLIC: clear_cache() — for manual invalidation
# ============================================================
def clear_cache() -> int:
    """Delete all cached entries. Returns count deleted."""
    try:
        _ensure_db()
        conn = sqlite3.connect(str(DB_PATH))
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM classifications")
            count = cursor.fetchone()[0]
            conn.execute("DELETE FROM classifications")
            conn.commit()
            log.info(f"Cache cleared: {count} entries removed")
            return count
        finally:
            conn.close()
    except Exception as e:
        log.warning(f"Cache clear error: {e}")
        return 0


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("CACHE MANAGER v2 — TEST")
    print("=" * 70)
    print(f"Prompt version: {PROMPT_VERSION}")
    print(f"Model name:     {MODEL_NAME}")

    # Clear old cache for clean test
    print(f"\n[0] Clearing old cache...")
    cleared = clear_cache()
    print(f"   Removed {cleared} old entries")

    # Test 1: Two DIFFERENT leads (previously collided)
    lead_a = {
        "lead_id": 0,
        "listing_type": "FSBO",
        "price_drop_pct": 15.0,
        "county": "Dallas",
        "owner_status": "owner_occupied",
        "distress_signals": "tax_delinquent",
    }
    lead_b = {
        "lead_id": 1,
        "listing_type": "FSBO",
        "price_drop_pct": 15.0,
        "county": "Dallas",
        "owner_status": "owner_occupied",
        "distress_signals": "",  # ← DIFFERENT distress
    }

    print(f"\n[1] Testing collision fix:")
    print(f"   Lead A distress: {lead_a['distress_signals']}")
    print(f"   Lead B distress: {lead_b['distress_signals']}")

    # Save A's result
    save_result(lead_a, "high_motivation", "Tax delinquent + FSBO")

    # Look up B (should be MISS — different hash)
    cached_b = get_cached(lead_b)
    print(f"   Lead B cache lookup: {cached_b}")
    print(f"   Expected: None (different leads → different keys)")

    # Save B
    save_result(lead_b, "moderate_motivation", "FSBO only")

    # Verify both cached separately
    cached_a = get_cached(lead_a)
    cached_b_after = get_cached(lead_b)
    print(f"\n   Lead A: {cached_a}")
    print(f"   Lead B: {cached_b_after}")
    print(f"   ✅ Collision fixed!" if cached_a != cached_b_after
          else "   ❌ STILL COLLIDING")

    # Test 2: Cache stats
    print(f"\n[2] Cache stats:")
    stats = cache_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")

    print("\n✅ Test complete")
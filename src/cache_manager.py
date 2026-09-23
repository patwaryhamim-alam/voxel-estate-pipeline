"""
CLASSIFICATION CACHE (SQLite) — v3
==================================
Caches AI classification results to avoid re-classifying same leads.

v2 FIX (CRITICAL):
    - Old key: listing_type + price_drop_pct + owner_status + county
      → Different leads with same values collided, causing WRONG cached results
    - New key: hash(ALL classification features + prompt version + model name)
      → Every unique lead gets unique key
      → Prompt changes auto-invalidate cache
      → Model changes auto-invalidate cache

v3 FIX (Fix 1 + Fix 3):
    - MODEL_NAME now reads from BOTH LLM_MODEL and GEMINI_MODEL env vars
      (matches llm_provider.py — previously they could disagree silently)
    - Docstring clarifies role in partial-run design

PARTIAL-RUN DESIGN (Fix 1):
    Cache is the PRIMARY state store for partial runs.
      - Classified leads → cached → next run = 0 API calls
      - Unclassified leads → not cached → next run = API call
      - No PII in cache — only classification features

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

# Fix 3: load .env so MODEL_NAME matches llm_provider.py exactly
from dotenv import load_dotenv
load_dotenv()

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
PROMPT_VERSION = "v3"

# Fix 3: read from BOTH env var names (matches llm_provider.py)
MODEL_NAME = (
    os.getenv("LLM_MODEL")
    or os.getenv("GEMINI_MODEL")
    or "gemini-3.5-flash"
)

# Fields EXCLUDED from hash (internal metadata — NOT part of lead identity)
EXCLUDE_FROM_HASH = {"lead_id"}

# Fields that get ROUNDED before hashing (avoid float noise)
ROUND_FIELDS = {"price_drop_pct"}


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
# HASHING (v3 — full payload + version + model)
# ============================================================
def _lead_hash(lead: Dict[str, Any]) -> str:
    """
    Create stable hash from classification-relevant fields.

    EXCLUDES:
        - lead_id (internal ref — same lead in two CSVs must hash same)

    ROUNDS:
        - price_drop_pct to 1 decimal (avoid float noise: 5.12 ≈ 5.13)

    INCLUDES:
        - PROMPT_VERSION (bump to invalidate all cache)
        - MODEL_NAME (auto-invalidates when model changes)
    """
    hash_input = {}

    for k, v in lead.items():
        if k in EXCLUDE_FROM_HASH:
            continue

        if k in ROUND_FIELDS:
            try:
                v = round(float(v), 1)
            except (ValueError, TypeError):
                v = 0.0

        hash_input[k] = v

    hash_input["_prompt_version"] = PROMPT_VERSION
    hash_input["_model_name"] = MODEL_NAME

    serialized = json.dumps(hash_input, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ============================================================
# PUBLIC: get_cached()
# ============================================================
def get_cached(lead: Dict[str, Any]) -> Optional[Dict]:
    """Get cached classification for a single lead."""
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

    Fix 1 usage: This is how partial-run state is tracked.
    Cached leads are already classified (skip API); uncached leads
    need processing on this run.
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

    lead_map = {lead["lead_id"]: lead for lead in original_leads}
    saved = 0

    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            for r in results:
                lead = lead_map.get(r["lead_id"])
                if not lead:
                    continue

                # Fix 1: skip caching "pending" results
                if r.get("signal_type") == "pending":
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
# PUBLIC: count_cached_for_batch()
# ============================================================
def count_cached_for_batch(leads: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Count cache hits/misses for a batch WITHOUT returning data.

    Fix 1 helper — for run summary "X/Y classified".

    ⚠️ Note: this increments hit_count. Only use for stats, not
    for actual classification flow. For classification, use get_many().
    """
    if not leads:
        return 0, 0

    _ensure_db()
    hits = 0
    misses = 0

    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            for lead in leads:
                h = _lead_hash(lead)
                cursor = conn.execute(
                    "SELECT 1 FROM classifications WHERE lead_hash = ? LIMIT 1",
                    (h,)
                )
                if cursor.fetchone():
                    hits += 1
                else:
                    misses += 1
        finally:
            conn.close()
    except Exception as e:
        log.warning(f"Cache count error: {e}")
        return 0, len(leads)

    return hits, misses


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("CACHE MANAGER v3 — TEST")
    print("=" * 70)
    print(f"Prompt version: {PROMPT_VERSION}")
    print(f"Model name:     {MODEL_NAME}")
    print(f"Env sources:    LLM_MODEL={os.getenv('LLM_MODEL')!r}  "
          f"GEMINI_MODEL={os.getenv('GEMINI_MODEL')!r}")

    print(f"\n[0] Clearing old cache...")
    cleared = clear_cache()
    print(f"   Removed {cleared} old entries")

    # Test 1: Collision fix (different distress → different hash)
    lead_a = {
        "lead_id": 0, "listing_type": "FSBO", "price_drop_pct": 15.0,
        "county": "Dallas", "owner_status": "owner_occupied",
        "distress_signals": "tax_delinquent",
    }
    lead_b = {
        "lead_id": 1, "listing_type": "FSBO", "price_drop_pct": 15.0,
        "county": "Dallas", "owner_status": "owner_occupied",
        "distress_signals": "",  # DIFFERENT
    }

    print(f"\n[1] Collision fix:")
    save_result(lead_a, "high_motivation", "Tax delinquent + FSBO")
    cached_b = get_cached(lead_b)
    print(f"   Lead B cache lookup: {cached_b}")
    print(f"   Expected: None (different distress → different key)")
    assert cached_b is None, "COLLISION BUG!"

    save_result(lead_b, "moderate_motivation", "FSBO only")
    cached_a = get_cached(lead_a)
    cached_b_after = get_cached(lead_b)
    print(f"   Lead A: {cached_a}")
    print(f"   Lead B: {cached_b_after}")
    assert cached_a != cached_b_after, "STILL COLLIDING"
    print("   OK Collision fixed")

    # Test 2: lead_id excluded from hash
    print(f"\n[2] lead_id exclusion:")
    lead_a2 = dict(lead_a, lead_id=999)  # same lead, different lead_id
    cached_a2 = get_cached(lead_a2)
    print(f"   Same lead with lead_id=999: {cached_a2}")
    print(f"   Expected: cache HIT (lead_id excluded)")
    assert cached_a2 is not None, "lead_id not excluded from hash!"
    print("   OK lead_id excluded")

    # Test 3: price_drop_pct rounding
    print(f"\n[3] Float noise rounding:")
    lead_c = dict(lead_a, lead_id=200, price_drop_pct=15.04999)
    cached_c = get_cached(lead_c)
    print(f"   15.04999 vs cached 15.0: {'HIT' if cached_c else 'MISS'}")
    print(f"   Expected: HIT (both round to 15.0)")

    # Test 4: pending skip
    print(f"\n[4] Pending NOT cached:")
    lead_p = dict(lead_a, lead_id=300, county="Travis")
    saved = save_many(
        [{"lead_id": 300, "signal_type": "pending", "reason": "quota"}],
        [lead_p],
    )
    print(f"   Saved count: {saved} (expected 0)")
    assert saved == 0, "Pending leaked into cache!"
    print("   OK Pending skipped")

    # Test 5: Stats
    print(f"\n[5] Cache stats:")
    stats = cache_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")

    print("\n✅ Cache manager test complete")
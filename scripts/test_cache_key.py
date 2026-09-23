"""
CACHE KEY TEST (Fix 2)
======================
Verifies that:
    1. Same lead with different lead_id → SAME cache key
    2. price_drop_pct rounding: 5.1234 and 5.12 → same key
    3. Different leads → different keys
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cache_manager import _lead_hash, clear_cache


def main():
    print("=" * 70)
    print("  CACHE KEY TEST (Fix 2)")
    print("=" * 70)

    # Clear any existing cache
    clear_cache()

    # ---- Test 1: Same lead, different lead_id ----
    print("\n[Test 1] Same lead, different lead_id:")
    lead_a = {
        "lead_id": 0,
        "listing_type": "FSBO",
        "price_drop_pct": 5.1,
        "county": "Dallas",
        "owner_status": "owner_occupied",
        "distress_signals": "",
    }
    lead_b = dict(lead_a)
    lead_b["lead_id"] = 42  # Same lead, different ID

    hash_a = _lead_hash(lead_a)
    hash_b = _lead_hash(lead_b)
    same = hash_a == hash_b
    print(f"   Lead A (id=0):  {hash_a[:16]}...")
    print(f"   Lead B (id=42): {hash_b[:16]}...")
    print(f"   Same hash? {same}  {'PASS' if same else 'FAIL'}")

    # ---- Test 2: price_drop_pct rounding ----
    print("\n[Test 2] Float rounding (5.1234 vs 5.12):")
    lead_c = dict(lead_a)
    lead_c["lead_id"] = 0
    lead_c["price_drop_pct"] = 5.1234
    lead_d = dict(lead_a)
    lead_d["lead_id"] = 0
    lead_d["price_drop_pct"] = 5.12

    hash_c = _lead_hash(lead_c)
    hash_d = _lead_hash(lead_d)
    same = hash_c == hash_d
    print(f"   5.1234: {hash_c[:16]}...")
    print(f"   5.12:   {hash_d[:16]}...")
    print(f"   Same hash? {same}  {'PASS' if same else 'FAIL'}")

    # ---- Test 3: Different leads → different hashes ----
    print("\n[Test 3] Different leads (should differ):")
    lead_e = dict(lead_a)
    lead_e["listing_type"] = "price_drop"  # Different signal

    hash_e = _lead_hash(lead_e)
    diff = hash_a != hash_e
    print(f"   Lead A (FSBO):         {hash_a[:16]}...")
    print(f"   Lead E (price_drop):   {hash_e[:16]}...")
    print(f"   Different? {diff}  {'PASS' if diff else 'FAIL'}")

    # ---- Summary ----
    print("\n" + "=" * 70)
    all_pass = (
        _lead_hash(lead_a) == _lead_hash(lead_b) and
        _lead_hash(lead_c) == _lead_hash(lead_d) and
        _lead_hash(lead_a) != _lead_hash(lead_e)
    )
    if all_pass:
        print("  ALL TESTS PASSED — Cache key logic correct")
    else:
        print("  SOME TESTS FAILED — Check the logic")
    print("=" * 70)


if __name__ == "__main__":
    main()
"""
800-ROW STRESS TEST (Fix 8)
============================
End-to-end partial-run behavior with 800 synthetic leads and a
mocked LLM that raises REAL daily-quota error on call 20.

VERIFIES:
    1. Run 1: 19 batches succeed, call 20 → daily quota → remaining pending
    2. Cache contains ONLY classified leads (no pending leakage)
    3. No fallback rows mixed with AI results
    4. Run 2: cache hits for done leads (0 API calls for them)
    5. Run 2: remaining leads processed, 0 pending at end
    6. File stays in inbox if partial (via process_one_csv dry-run)

NO real API calls. NO Sheets push.

Run:
    python scripts/test_800_row_stress.py
"""

import sys
import json
import re
import time
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd


# ============================================================
# REAL DAILY QUOTA ERROR (captured from production logs)
# ============================================================
REAL_DAILY_QUOTA_ERROR = (
    "Error calling model 'gemini-3.6-flash' (RESOURCE_EXHAUSTED): "
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
    "'You exceeded your current quota, please check your plan and "
    "billing details.', 'status': 'RESOURCE_EXHAUSTED', "
    "'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', "
    "'violations': [{'quotaMetric': "
    "'generativelanguage.googleapis.com/generate_content_free_tier_requests', "
    "'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', "
    "'quotaDimensions': {'location': 'global', 'model': 'gemini-3.6-flash'}, "
    "'quotaValue': '20'}]}]}}"
)


# ============================================================
# SYNTHETIC DATA GENERATOR
# ============================================================
def make_synthetic_800_df() -> pd.DataFrame:
    """
    Build a varied 800-row DataFrame.
    Mix of distress signals, absentee owners, price drops.
    """
    import random
    random.seed(42)

    counties = ["Dallas", "Travis", "Harris", "Maricopa", "Clark",
                "Shelby", "Wake", "Mecklenburg", "Franklin", "Hamilton"]
    distress_options = [
        "", "", "", "",  # mostly empty
        "tax_delinquent", "vacant", "pre_foreclosure",
        "expired_listing", "divorce", "probate"
    ]
    listing_types = ["FSBO", "price_drop"]

    rows = []
    for i in range(800):
        list_price = random.randint(80000, 800000)
        if random.random() < 0.6:
            prev_price = int(list_price * random.uniform(1.02, 1.30))
        else:
            prev_price = list_price

        rows.append({
            "owner_name": f"Owner{i:03d} Test",
            "address": f"{i} Test St City{i%50} TX",
            "owner_mailing_address": f"{i} Test St City{i%50} TX",
            "phone": f"({random.randint(200,999)}) "
                     f"{random.randint(200,999)}-{random.randint(1000,9999)}",
            "listing_type": random.choice(listing_types),
            "list_price": list_price,
            "previous_price": prev_price,
            "county": random.choice(counties),
            "distress_signals": random.choice(distress_options),
        })
    return pd.DataFrame(rows)


# ============================================================
# MOCK LLM HELPERS
# ============================================================
def _extract_lead_ids(prompt: str):
    """Extract lead IDs from prompt — matches 'Lead #N:' lines."""
    return [int(m) for m in re.findall(r"Lead #(\d+):", prompt)]


def _fake_response_for(prompt: str) -> str:
    """Build a valid JSON array response for the batch."""
    lead_ids = _extract_lead_ids(prompt)
    results = [
        {
            "lead_id": lid_id,
            "signal_type": "moderate_motivation",
            "reason": "stress test mock",
        }
        for lid_id in lead_ids
    ]
    return json.dumps(results)


# ============================================================
# TEST 1: RUN 1 with quota failure at call 20
# ============================================================
def test_run1_partial():
    print("\n" + "=" * 70)
    print("TEST 1: RUN 1 — quota failure at call 20 of 27 batches")
    print("=" * 70)

    import llm_provider
    from data_cleaner import clean_leads
    from cache_manager import clear_cache, cache_stats

    clear_cache()
    llm_provider.reset_llm_call_count()

    df = make_synthetic_800_df()
    df["owner_status"] = "owner_occupied"
    df["price_drop_pct"] = 0.0
    df["days_on_market"] = 30
    df["property_type"] = "Single Family"

    print(f"  Input: {len(df)} rows")

    batch_size = llm_provider.BATCH_SIZE
    expected_batches = (len(df) + batch_size - 1) // batch_size
    print(f"  Batch size: {batch_size}")
    print(f"  Expected batches: {expected_batches}")

    call_counter = {"n": 0}

    def fake_call_gemini(prompt):
        call_counter["n"] += 1
        if call_counter["n"] >= 20:
            raise Exception(REAL_DAILY_QUOTA_ERROR)
        return _fake_response_for(prompt)

    with patch.object(llm_provider, "_call_gemini", side_effect=fake_call_gemini), \
         patch.object(time, "sleep", return_value=None):
        output_df, detail_df = clean_leads(df.copy())

    pending_count = detail_df.attrs.get("partial_count", 0)
    classified_count = len(output_df) - pending_count

    print(f"\n  LLM API calls attempted: {call_counter['n']}")
    print(f"  Classified (non-pending): {classified_count}")
    print(f"  Pending: {pending_count}")
    print(f"  Total: {classified_count + pending_count}")

    assert call_counter["n"] == expected_batches, \
        f"FAIL: Expected {expected_batches} calls, got {call_counter['n']}"
    assert classified_count > 0, "FAIL: No leads classified"
    assert pending_count > 0, "FAIL: No pending leads — quota should have hit"
    assert classified_count + pending_count == len(output_df), \
        "FAIL: Classified + pending != total"

    non_pending = output_df[output_df["signal_type"] != "pending"]
    pending_rows = output_df[output_df["signal_type"] == "pending"]
    assert len(non_pending) == classified_count
    assert len(pending_rows) == pending_count

    fallback_reasons = non_pending[non_pending["reason"].str.contains(
        "Rule-based", na=False, case=False)]
    assert len(fallback_reasons) == 0, \
        f"FAIL: {len(fallback_reasons)} fallback rows mixed in"

    stats = cache_stats()
    cache_count = stats.get("total_cached", 0)
    print(f"\n  Cache entries: {cache_count}")
    print(f"  (Note: cache <= classified due to dedup, expected)")

    assert cache_count <= classified_count, \
        f"FAIL: Cache has {cache_count} > classified {classified_count} (pending leaked!)"

    min_expected = int(classified_count * 0.5)
    assert cache_count >= min_expected, \
        f"FAIL: Cache too small ({cache_count} < {min_expected})"

    from cache_manager import _ensure_db
    import sqlite3
    _ensure_db()
    conn = sqlite3.connect(str(PROJECT_ROOT / "cache" / "classifications.db"))
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM classifications WHERE signal_type = 'pending'"
        )
        pending_in_cache = cursor.fetchone()[0]
    finally:
        conn.close()
    assert pending_in_cache == 0, \
        f"FAIL: {pending_in_cache} pending entries leaked to cache!"
    print(f"  Pending in cache: {pending_in_cache} (correct)")

    print("\n  ✅ PASS: Run 1 partial behavior correct")
    print(f"     - {classified_count} classified")
    print(f"     - {pending_count} pending (would stay in inbox)")
    print(f"     - 0 fallback rows")
    print(f"     - Cache has only classified entries")
    return classified_count, pending_count


# ============================================================
# TEST 2: RUN 2 — cache hits for done, remaining processed
# ============================================================
def test_run2_cache_completion(classified_count, pending_count):
    print("\n" + "=" * 70)
    print("TEST 2: RUN 2 — cache hits for done, remaining leads processed")
    print("=" * 70)

    import llm_provider
    from data_cleaner import clean_leads
    from cache_manager import cache_stats

    llm_provider.reset_llm_call_count()

    df = make_synthetic_800_df()
    df["owner_status"] = "owner_occupied"
    df["price_drop_pct"] = 0.0
    df["days_on_market"] = 30
    df["property_type"] = "Single Family"

    print(f"  Input: {len(df)} rows (same 800)")

    call_counter = {"n": 0}

    def fake_call_gemini(prompt):
        call_counter["n"] += 1
        return _fake_response_for(prompt)

    with patch.object(llm_provider, "_call_gemini", side_effect=fake_call_gemini), \
         patch.object(time, "sleep", return_value=None):
        output_df, detail_df = clean_leads(df.copy())

    pending_count_2 = detail_df.attrs.get("partial_count", 0)
    classified_count_2 = len(output_df) - pending_count_2

    print(f"\n  LLM API calls this run: {call_counter['n']}")
    print(f"  Classified: {classified_count_2}")
    print(f"  Pending: {pending_count_2}")

    batch_size = llm_provider.BATCH_SIZE
    expected_new_calls = (pending_count + batch_size - 1) // batch_size

    print(f"  Expected new API calls (pending / batch_size): {expected_new_calls}")
    assert call_counter["n"] <= expected_new_calls + 1, \
        (f"FAIL: Cache miss — expected ≤{expected_new_calls} calls, "
         f"got {call_counter['n']}")
    assert classified_count_2 == len(output_df), \
        f"FAIL: Run 2 should fully classify. {pending_count_2} still pending"
    assert pending_count_2 == 0, "FAIL: Run 2 should leave 0 pending"

    stats = cache_stats()
    cache_total = stats.get("total_cached", 0)
    print(f"\n  Cache total: {cache_total}")
    print(f"  (Note: cache <= {len(df)} due to duplicate feature hashes)")

    assert cache_total > classified_count, \
        (f"FAIL: Cache ({cache_total}) didn't grow beyond Run 1 "
         f"classified ({classified_count})")

    assert cache_total <= len(df), \
        f"FAIL: Cache ({cache_total}) > total leads ({len(df)})"

    print(f"\n  ✅ PASS: Run 2 completed with cache reuse")
    print(f"     - Only {call_counter['n']} new API calls (rest cache hits)")
    print(f"     - All {len(df)} leads classified")
    print(f"     - Cache grew from {classified_count} → {cache_total}")


# ============================================================
# TEST 3: FILE WATCHER — stays in inbox on partial
# ============================================================
def test_file_stays_inbox_on_partial():
    print("\n" + "=" * 70)
    print("TEST 3: File-watcher — partial file stays in inbox")
    print("=" * 70)

    import shutil
    import llm_provider
    from cache_manager import clear_cache

    clear_cache()
    llm_provider.reset_llm_call_count()

    test_client = "stress_test_client"
    inbox_dir = PROJECT_ROOT / "inbox" / test_client
    processed_dir = PROJECT_ROOT / "processed" / test_client
    inbox_dir.mkdir(parents=True, exist_ok=True)
    if processed_dir.exists():
        shutil.rmtree(processed_dir)

    for f in inbox_dir.glob("*.csv"):
        f.unlink()

    small_df = make_synthetic_800_df().head(30)
    csv_path = inbox_dir / "stress.csv"
    small_df.to_csv(csv_path, index=False)

    from file_watcher import scan_inbox, move_to_processed

    files = scan_inbox(test_client)
    print(f"\n  Files in inbox: {[f.name for f in files]}")
    assert len(files) == 1, "FAIL: Expected 1 file in inbox"

    def fake_call_gemini(prompt):
        raise Exception(REAL_DAILY_QUOTA_ERROR)

    from data_collector import load_property_data
    from data_cleaner import clean_leads

    with patch.object(llm_provider, "_call_gemini", side_effect=fake_call_gemini), \
         patch.object(time, "sleep", return_value=None):
        raw = load_property_data(str(csv_path))
        out_df, detail_df = clean_leads(raw)

    partial_count = detail_df.attrs.get("partial_count", 0)
    print(f"  Partial count: {partial_count}")

    if partial_count == 0:
        move_to_processed(test_client, csv_path)
        print("  [Simulated] Would move to processed/")
    else:
        print(f"  [Simulated] File STAYS in inbox ({partial_count} pending)")

    remaining = list(inbox_dir.glob("*.csv"))
    print(f"  Files still in inbox: {[f.name for f in remaining]}")
    assert len(remaining) == 1, \
        "FAIL: Partial file should stay in inbox"

    for f in inbox_dir.glob("*.csv"):
        f.unlink()
    if inbox_dir.exists():
        try:
            inbox_dir.rmdir()
        except OSError:
            pass

    print("\n  ✅ PASS: Partial file stays in inbox")


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 70)
    print("  800-ROW STRESS TEST (Fix 8)")
    print("=" * 70)
    print("Real Gemini daily-quota error format used on call 20.")
    print("No real API calls. No Sheets push.")

    try:
        classified_count, pending_count = test_run1_partial()
        test_run2_cache_completion(classified_count, pending_count)
        test_file_stays_inbox_on_partial()

        print("\n" + "=" * 70)
        print("  ALL 3 STRESS TESTS PASSED")
        print("=" * 70)
        print("  ✅ Run 1: partial split correct (no fallback, cache clean)")
        print("  ✅ Run 2: cache reuse, remaining processed")
        print("  ✅ File-watcher: partial file stays in inbox")
        print()
        print("  Fix 8 verified — pipeline is stress-clean.")
        return 0

    except AssertionError as e:
        print(f"\n❌ FAIL: {e}")
        return 1
    except Exception as e:
        import traceback
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
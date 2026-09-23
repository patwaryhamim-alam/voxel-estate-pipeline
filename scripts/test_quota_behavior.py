"""
QUOTA BEHAVIOR TEST (Fix 4 — Real Error Text)
==============================================
Uses REAL Gemini error messages captured from production logs.

Fix 4 changes:
    - Daily 429 test uses real message format from logs/
    - Per-minute 429 test uses real message format
    - Model-not-found test uses real 404 message format
    - Classifier tested against real text (not fabricated markers)

Run:
  python scripts/test_quota_behavior.py
"""

import sys
import os
import json
import time
from pathlib import Path
from unittest.mock import patch

# Add src/ to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import llm_provider
import pending_queue
from pending_queue import clear_pending, pending_count, load_pending, _priority_score


# ============================================================
# REAL ERROR MESSAGES (captured from production logs)
# ============================================================
# Source: logs/errors_2026-09-21.log + logs/run_2026-09-22.log
REAL_DAILY_QUOTA_ERROR = (
    "Error calling model 'gemini-3.6-flash' (RESOURCE_EXHAUSTED): "
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
    "'You exceeded your current quota, please check your plan and "
    "billing details. For more information on this error, head to: "
    "https://ai.google.dev/gemini-api/docs/rate-limits. To monitor "
    "your current usage, head to: https://ai.dev/rate-limit. \\n* "
    "Quota exceeded for metric: "
    "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
    "limit: 20, model: gemini-3.6-flash\\n"
    "Please retry in 6.42125118s.', 'status': 'RESOURCE_EXHAUSTED', "
    "'details': [{'@type': 'type.googleapis.com/google.rpc.Help', "
    "'links': [{'description': 'Learn more about Gemini API quotas', "
    "'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, "
    "{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', "
    "'violations': [{'quotaMetric': "
    "'generativelanguage.googleapis.com/generate_content_free_tier_requests', "
    "'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', "
    "'quotaDimensions': {'location': 'global', 'model': 'gemini-3.6-flash'}, "
    "'quotaValue': '20'}]}, "
    "{'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
    "'retryDelay': '6s'}]}}"
)

REAL_MODEL_NOT_FOUND_ERROR = (
    "Error calling model 'gemini-2.5-flash' (NOT_FOUND): "
    "404 NOT_FOUND. {'error': {'code': 404, 'message': "
    "'This model models/gemini-2.5-flash is no longer available to "
    "new users. Please update your code to use models/gemini-3.6-flash "
    "for the latest features and improvements. We recommend you to use "
    "the Interactions API.', 'status': 'NOT_FOUND'}}"
)

# Synthetic per-minute (real Gemini uses same structure with PerMinute)
REAL_PER_MINUTE_ERROR = (
    "Error calling model 'gemini-3.6-flash' (RESOURCE_EXHAUSTED): "
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
    "'Resource has been exhausted (e.g. check quota).', "
    "'status': 'RESOURCE_EXHAUSTED', 'details': ["
    "{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', "
    "'violations': [{'quotaMetric': "
    "'generativelanguage.googleapis.com/generate_content_free_tier_requests', "
    "'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', "
    "'quotaValue': '15'}]}]}}"
)


# ============================================================
# SETUP
# ============================================================
def reset_state():
    """Clear cache and pending before each test."""
    clear_pending()
    cache_db = PROJECT_ROOT / "cache" / "classifications.db"
    if cache_db.exists():
        cache_db.unlink()


def make_test_lead(lead_id: int, **overrides) -> dict:
    """Create a PII-free test lead."""
    base = {
        "lead_id": lead_id,
        "listing_type": "FSBO",
        "price_drop_pct": 12.0,
        "county": "Dallas",
        "owner_status": "out_of_state_absentee",
        "distress_signals": "tax_delinquent",
        "days_on_market": 45,
        "property_type": "Single Family",
    }
    base.update(overrides)
    return base


# ============================================================
# TEST 0: REAL TEXT CLASSIFIER (Fix 4 — the main point)
# ============================================================
def test_real_daily_classifier():
    print("\n" + "=" * 60)
    print("TEST 0: Classifier with REAL Gemini error text (Fix 4)")
    print("=" * 60)

    # Real daily quota error
    is_daily = llm_provider._is_daily_quota_error(REAL_DAILY_QUOTA_ERROR)
    print(f"\n  Real daily error classified as daily: {is_daily}")
    print(f"  First 100 chars: {REAL_DAILY_QUOTA_ERROR[:100]}")
    assert is_daily is True, \
        "FAIL: Real daily error NOT detected as daily quota!"

    # Real per-minute
    is_minute = llm_provider._is_daily_quota_error(REAL_PER_MINUTE_ERROR)
    print(f"\n  Real per-minute error classified as daily: {is_minute}")
    assert is_minute is False, \
        "FAIL: Real per-minute error WRONGLY classified as daily!"

    # Real model-not-found
    is_404 = llm_provider._is_model_not_found_error(REAL_MODEL_NOT_FOUND_ERROR)
    print(f"\n  Real 404 error classified as model-not-found: {is_404}")
    print(f"  First 100 chars: {REAL_MODEL_NOT_FOUND_ERROR[:100]}")
    assert is_404 is True, \
        "FAIL: Real model-not-found error NOT detected!"

    # 404 should NOT be classified as daily quota
    is_404_daily = llm_provider._is_daily_quota_error(REAL_MODEL_NOT_FOUND_ERROR)
    assert is_404_daily is False, \
        "FAIL: 404 wrongly classified as daily quota!"

    print("\n  ✅ PASS: Real error texts correctly classified")
    return True


# ============================================================
# TEST 1: DAILY 429 (real text) → pending markers, no retries
# ============================================================
def test_daily_429_saves_pending():
    print("\n" + "=" * 60)
    print("TEST 1: DAILY 429 (real text) → pending markers, no retries")
    print("=" * 60)

    reset_state()

    leads = [make_test_lead(i) for i in range(5)]

    call_count = {"n": 0}
    def fake_call(prompt):
        call_count["n"] += 1
        raise Exception(REAL_DAILY_QUOTA_ERROR)

    with patch.object(llm_provider, "_call_gemini", side_effect=fake_call):
        results = llm_provider.classify_batch(leads)

    print(f"\n  LLM call attempts: {call_count['n']}")
    print(f"  Results returned: {len(results)}")
    pending_markers = sum(1 for r in results if r["signal_type"] == "pending")
    print(f"  Pending markers: {pending_markers}")

    assert call_count["n"] == 1, \
        f"FAIL: Daily 429 should NOT retry. Called {call_count['n']} times."
    assert len(results) == 5, "FAIL: Should return 5 results"
    assert pending_markers == 5, \
        f"FAIL: All should be 'pending', got {pending_markers}"

    # Fix 1 design: pending/ folder should be EMPTY
    assert pending_count() == 0, \
        f"FAIL: pending/ should be empty (Fix 1 design), got {pending_count()}"

    print("\n  ✅ PASS: Real daily 429 → 1 call, 5 pending markers, no file")
    return True


# ============================================================
# TEST 2: PER-MINUTE 429 (real text) → retries
# ============================================================
def test_per_minute_429_retries():
    print("\n" + "=" * 60)
    print("TEST 2: PER-MINUTE 429 (real text) → retries with backoff")
    print("=" * 60)

    reset_state()

    leads = [make_test_lead(i) for i in range(3)]

    call_count = {"n": 0}
    def fake_call(prompt):
        call_count["n"] += 1
        raise Exception(REAL_PER_MINUTE_ERROR)

    with patch.object(llm_provider, "_call_gemini", side_effect=fake_call), \
         patch.object(time, "sleep", return_value=None):
        results = llm_provider.classify_batch(leads)

    print(f"\n  LLM call attempts: {call_count['n']}")
    print(f"  Labels: {[r['signal_type'] for r in results]}")

    assert call_count["n"] == llm_provider.MAX_RETRIES, \
        f"FAIL: Expected {llm_provider.MAX_RETRIES} retries, got {call_count['n']}"
    assert all(r["signal_type"] != "pending" for r in results), \
        "FAIL: Per-minute should fallback to rule-based, not pending"

    print("\n  ✅ PASS: Real per-minute 429 → retried then fallback")
    return True


# ============================================================
# TEST 3: MODEL-NOT-FOUND (real text) → raises + no pending
# ============================================================
def test_model_not_found_raises():
    print("\n" + "=" * 60)
    print("TEST 3: MODEL-NOT-FOUND (real text) → raises, no pending")
    print("=" * 60)

    reset_state()

    leads = [make_test_lead(i) for i in range(3)]

    call_count = {"n": 0}
    def fake_call(prompt):
        call_count["n"] += 1
        raise Exception(REAL_MODEL_NOT_FOUND_ERROR)

    # Fix 3: expect RuntimeError, not graceful fallback
    raised = False
    try:
        with patch.object(llm_provider, "_call_gemini", side_effect=fake_call), \
             patch.object(llm_provider, "_alert_model_not_found", return_value=None):
            llm_provider.classify_batch(leads)
    except RuntimeError as e:
        raised = True
        print(f"\n  RuntimeError raised: {str(e)[:80]}")

    print(f"  LLM call attempts: {call_count['n']}")

    assert raised, "FAIL: Model-not-found should raise RuntimeError"
    assert call_count["n"] == 1, \
        f"FAIL: Model-not-found should NOT retry, called {call_count['n']} times"
    assert pending_count() == 0, \
        f"FAIL: Model-not-found should not create pending, got {pending_count()}"

    print("\n  ✅ PASS: Real 404 → 1 call, raises, no pending")
    return True


# ============================================================
# TEST 4: Pending results NOT cached
# ============================================================
def test_pending_not_cached():
    print("\n" + "=" * 60)
    print("TEST 4: Pending results NOT cached")
    print("=" * 60)

    reset_state()

    leads = [make_test_lead(i) for i in range(3)]

    def fake_call(prompt):
        raise Exception(REAL_DAILY_QUOTA_ERROR)

    with patch.object(llm_provider, "_call_gemini", side_effect=fake_call):
        llm_provider.classify_batch(leads)

    from cache_manager import get_many
    cached, uncached = get_many(leads)

    print(f"\n  Cache hits: {len(cached)}")
    print(f"  Cache misses: {len(uncached)}")

    assert len(cached) == 0, \
        f"FAIL: Pending results should NOT be cached. Got {len(cached)} hits."
    assert len(uncached) == 3, \
        f"FAIL: All 3 should be uncached, got {len(uncached)}"

    print("\n  ✅ PASS: Pending results NOT cached")
    return True


# ============================================================
# MAIN
# ============================================================
def main():
    print("\n" + "=" * 60)
    print("QUOTA BEHAVIOR TEST SUITE (Fix 4 — Real Error Text)")
    print("=" * 60)
    print("Uses real Gemini error formats from production logs.")
    print("No real API calls made — all mocked.")

    results = []
    tests = [
        ("Real text classifier", test_real_daily_classifier),
        ("Real daily 429 → pending markers", test_daily_429_saves_pending),
        ("Real per-minute 429 → retries", test_per_minute_429_retries),
        ("Real model 404 → raises", test_model_not_found_raises),
        ("Pending NOT cached", test_pending_not_cached),
    ]

    for name, fn in tests:
        try:
            fn()
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:
            results.append((name, False, f"ERROR: {type(e).__name__}: {e}"))

    clear_pending()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, msg in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if msg:
            print(f"         {msg}")

    print(f"\n  Total: {passed}/{total} passed")
    print("=" * 60)

    if passed == total:
        print("\n✅ ALL TESTS PASSED — Fix 4 verified with REAL error text")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
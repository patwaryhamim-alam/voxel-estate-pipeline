"""
SMOKE TEST — Voxel Estate Pipeline
===================================
End-to-end verification of all modules WITHOUT real API calls.

WHAT IT TESTS:
    [1] Imports — all modules load without error
    [2] Adapters — 3 formats (PropStream, BatchLeads, Standard)
    [3] Cache — set/get/clear roundtrip
    [4] Pending Queue — save/load/priority-sort/clear
    [5] Logger — trimmed traceback
    [6] LLM Provider — pending markers on daily 429 (Fix 1)
    [7] End-to-End — dry-run on sample CSV (mock LLM)

EXIT CODES:
    0 = all pass (CI-ready)
    1 = at least one failure

USAGE:
    python scripts/smoke_test.py
    python scripts/smoke_test.py -v

RUNTIME: ~10 seconds (no network calls)
"""

import argparse
import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ============================================================
# TEST FRAMEWORK
# ============================================================
class TestRunner:
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.passed = 0
        self.failed = 0
        self.results = []

    def run(self, name, fn):
        try:
            if self.verbose:
                fn()
            else:
                with redirect_stdout(io.StringIO()), \
                     redirect_stderr(io.StringIO()):
                    fn()

            self.passed += 1
            self.results.append((name, True, ""))
            print(f"  [PASS] {name}")
            return True
        except AssertionError as e:
            self.failed += 1
            self.results.append((name, False, f"ASSERT: {e}"))
            print(f"  [FAIL] {name}")
            print(f"         {e}")
            return False
        except Exception as e:
            self.failed += 1
            tb_short = traceback.format_exc().split("\n")[-3]
            self.results.append((name, False, f"ERROR: {type(e).__name__}: {e}"))
            print(f"  [FAIL] {name}")
            print(f"         {type(e).__name__}: {str(e)[:120]}")
            if self.verbose:
                print(f"         {tb_short}")
            return False

    def summary(self):
        total = self.passed + self.failed
        print()
        print("=" * 60)
        print(f"SMOKE TEST SUMMARY: {self.passed}/{total} passed")
        print("=" * 60)
        if self.failed == 0:
            print("  ALL TESTS PASSED — pipeline is smoke-clean")
            return 0
        else:
            print(f"  {self.failed} TEST(S) FAILED:")
            for name, ok, msg in self.results:
                if not ok:
                    print(f"    - {name}: {msg}")
            return 1


# ============================================================
# TEST 1: IMPORTS
# ============================================================
def test_imports():
    """All modules must import without error."""
    import adapter
    import absentee_detector
    import cache_manager
    import data_cleaner
    import data_collector
    import file_watcher
    import llm_provider
    import logger
    import pending_queue
    import run_summary
    import us_validators

    assert hasattr(adapter, "adapt_generic"), "adapter.adapt_generic missing"
    assert hasattr(llm_provider, "classify_batch"), "llm_provider.classify_batch missing"
    assert hasattr(llm_provider, "get_llm_call_count"), "get_llm_call_count missing"
    assert hasattr(pending_queue, "save_pending"), "pending_queue.save_pending missing"
    assert hasattr(pending_queue, "_priority_score"), "_priority_score missing"


# ============================================================
# TEST 2: ADAPTERS
# ============================================================
def test_adapter_propstream():
    """PropStream format with days/type."""
    import pandas as pd
    from adapter import adapt_generic, EXPECTED_COLUMNS

    df = pd.DataFrame({
        "Owner First Name": ["John"],
        "Owner Last Name": ["Smith"],
        "Property Address": ["123 Oak St"],
        "City": ["Dallas"],
        "State": ["TX"],
        "County Name": ["Dallas"],
        "Listing Price": ["185000"],
        "Original Price": ["195000"],
        "For Sale By Owner": ["Yes"],
        "Days on Market": ["45"],
        "Property Type": ["Single Family"],
    })
    out = adapt_generic(df)

    for col in EXPECTED_COLUMNS:
        assert col in out.columns, f"Missing column: {col}"

    assert out.iloc[0]["owner_name"] == "John Smith"
    assert out.iloc[0]["days_on_market"] == 45
    assert out.iloc[0]["property_type"] == "Single Family"
    assert "Dallas" in out.iloc[0]["address"]


def test_adapter_batchleads():
    """BatchLeads format (full name, no days/type)."""
    import pandas as pd
    from adapter import adapt_generic

    df = pd.DataFrame({
        "Owner Name": ["David Wilson"],
        "Property Street": ["654 Cedar Ln"],
        "Property City": ["Plano"],
        "State": ["TX"],
        "Asking Price": ["120000"],
        "Original Price": ["135000"],
    })
    out = adapt_generic(df)

    assert out.iloc[0]["owner_name"] == "David Wilson"
    assert out.iloc[0]["days_on_market"] is None or pd.isna(out.iloc[0]["days_on_market"])
    assert out.iloc[0]["property_type"] is None or pd.isna(out.iloc[0]["property_type"])


def test_adapter_missing_address():
    """Adapter must raise clear error when address column missing."""
    import pandas as pd
    from adapter import adapt_generic

    df = pd.DataFrame({"Foo": ["bar"], "Baz": ["qux"]})
    try:
        adapt_generic(df)
        assert False, "Expected ValueError for missing address column"
    except ValueError as e:
        assert "address" in str(e).lower()


# ============================================================
# TEST 3: CACHE
# ============================================================
def test_cache_roundtrip():
    """Cache set/get/clear works with prompt-versioned keys."""
    from cache_manager import get_many, save_many, clear_cache

    clear_cache()

    leads = [
        {
            "lead_id": 0, "listing_type": "FSBO", "price_drop_pct": 12.0,
            "county": "Dallas", "owner_status": "out_of_state_absentee",
            "distress_signals": "tax_delinquent",
            "days_on_market": 45, "property_type": "Single Family",
        },
        {
            "lead_id": 1, "listing_type": "price_drop", "price_drop_pct": 5.0,
            "county": "Travis", "owner_status": "owner_occupied",
            "distress_signals": "",
            "days_on_market": 20, "property_type": "Condo",
        },
    ]

    results = [
        {"lead_id": 0, "signal_type": "high_motivation", "reason": "test"},
        {"lead_id": 1, "signal_type": "moderate_motivation", "reason": "test"},
    ]

    saved = save_many(results, leads)
    assert saved == 2, f"Expected 2 saved, got {saved}"

    cached, uncached = get_many(leads)
    assert len(cached) == 2, f"Expected 2 cache hits, got {len(cached)}"
    assert len(uncached) == 0, f"Expected 0 misses, got {len(uncached)}"

    clear_cache()


def test_cache_distress_invalidates():
    """Different distress signals → different cache keys."""
    from cache_manager import get_many, save_many, clear_cache

    clear_cache()

    lead_a = {
        "lead_id": 0, "listing_type": "FSBO", "price_drop_pct": 10.0,
        "county": "Dallas", "owner_status": "owner_occupied",
        "distress_signals": "tax_delinquent",
        "days_on_market": 30, "property_type": "Single Family",
    }
    lead_b = dict(lead_a, lead_id=1, distress_signals="")

    save_many(
        [{"lead_id": 0, "signal_type": "high_motivation", "reason": "x"}],
        [lead_a],
    )

    cached, uncached = get_many([lead_b])
    assert len(cached) == 0, "Lead B should miss cache (different distress)"

    clear_cache()


# ============================================================
# TEST 4: PENDING QUEUE
# ============================================================
def test_pending_roundtrip():
    """Save, load, count, clear."""
    from pending_queue import (
        save_pending, load_pending, pending_count, clear_pending, has_pending,
    )

    clear_pending()
    assert pending_count() == 0
    assert not has_pending()

    leads = [{"lead_id": i, "distress_signals": "", "owner_status": "owner_occupied",
              "price_drop_pct": 5.0} for i in range(3)]
    save_pending(leads, reason="test")

    assert pending_count() == 3
    assert has_pending()

    loaded = load_pending()
    assert len(loaded) == 3

    cleared = clear_pending()
    assert cleared >= 1
    assert pending_count() == 0


def test_pending_priority_sort():
    """Distress > OOS absentee > in-state > price drop."""
    from pending_queue import load_pending, save_pending, clear_pending, _priority_score

    clear_pending()

    leads = [
        {"lead_id": 0, "owner_status": "owner_occupied", "distress_signals": "",
         "price_drop_pct": 2.0},
        {"lead_id": 1, "owner_status": "owner_occupied",
         "distress_signals": "tax_delinquent", "price_drop_pct": 5.0},
        {"lead_id": 2, "owner_status": "out_of_state_absentee",
         "distress_signals": "", "price_drop_pct": 8.0},
        {"lead_id": 3, "owner_status": "in_state_absentee",
         "distress_signals": "", "price_drop_pct": 3.0},
    ]
    save_pending(leads, reason="test")

    loaded = load_pending()
    ids = [l["lead_id"] for l in loaded]

    assert ids[0] == 1, f"Expected lead 1 first, got {ids}"
    assert ids[-1] == 0, f"Expected lead 0 last, got {ids}"

    scores = [_priority_score(l) for l in loaded]
    assert scores == sorted(scores, reverse=True), "Not sorted by priority"

    clear_pending()


# ============================================================
# TEST 5: LOGGER
# ============================================================
def test_logger_trimmed_traceback():
    """Logger trims deep tracebacks."""
    import logging
    from logger import get_logger, _TrimmedFormatter

    def lvl5(): return 1 / 0
    def lvl4(): return lvl5()
    def lvl3(): return lvl4()
    def lvl2(): return lvl3()
    def lvl1(): return lvl2()

    try:
        lvl1()
    except ZeroDivisionError:
        ei = sys.exc_info()
        fmt = _TrimmedFormatter("%(message)s")
        formatted = fmt.formatException(ei)

        assert "trimmed" in formatted.lower(), "Missing 'trimmed' marker"
        frame_count = formatted.count("File \"")
        assert frame_count <= 8, f"Too many frames kept: {frame_count}"


# ============================================================
# TEST 6: LLM PROVIDER (no API call)
# ============================================================
def test_llm_quota_classifier():
    """Daily vs per-minute detection."""
    from llm_provider import _is_daily_quota_error

    daily = [
        "429 RESOURCE_EXHAUSTED: GenerateRequestsPerDayPerProjectPerModel",
        "daily limit reached",
        'quota_value": 1500',
    ]
    for msg in daily:
        assert _is_daily_quota_error(msg) is True, f"Missed daily: {msg}"

    minute = [
        "429 RESOURCE_EXHAUSTED: GenerateRequestsPerMinutePerProjectPerModel",
        "Rate limit exceeded",
    ]
    for msg in minute:
        assert _is_daily_quota_error(msg) is False, f"Wrong per-minute: {msg}"

    assert _is_daily_quota_error("429") is False


def test_llm_model_not_found_classifier():
    """Model-not-found detection (Fix 3)."""
    from llm_provider import _is_model_not_found_error

    cases = [
        "404 model not found",
        "Invalid model name",
        "Model does not exist",
        "unsupported model",
    ]
    for msg in cases:
        assert _is_model_not_found_error(msg) is True, f"Missed: {msg}"

    assert _is_model_not_found_error("429 rate limit") is False
    assert _is_model_not_found_error("generic error") is False


def test_llm_rule_based_fallback():
    """Rule-based fallback classifies correctly (DOM rules matched with prompt)."""
    from llm_provider import _fallback_classify

    # High: distress signal
    r = _fallback_classify({
        "lead_id": 0, "listing_type": "price_drop", "price_drop_pct": 3.0,
        "owner_status": "owner_occupied", "distress_signals": "tax_delinquent",
    })
    assert r["signal_type"] == "high_motivation"

    # Low: no signals
    r = _fallback_classify({
        "lead_id": 1, "listing_type": "price_drop", "price_drop_pct": 0.0,
        "owner_status": "owner_occupied", "distress_signals": "",
    })
    assert r["signal_type"] == "low_motivation"

    # LLC without signals → low (not boosted)
    r = _fallback_classify({
        "lead_id": 2, "listing_type": "price_drop", "price_drop_pct": 0.0,
        "owner_status": "llc_or_trust_owner", "distress_signals": "",
    })
    assert r["signal_type"] == "low_motivation"

    # Fix 1: DOM > 180 → high (matches prompt rule)
    r = _fallback_classify({
        "lead_id": 3, "listing_type": "price_drop", "price_drop_pct": 3.0,
        "owner_status": "owner_occupied", "distress_signals": "",
        "days_on_market": 200,
    })
    assert r["signal_type"] == "high_motivation", \
        f"DOM>180 should be high, got {r['signal_type']}"

    # DOM 90-180 → moderate
    r = _fallback_classify({
        "lead_id": 4, "listing_type": "price_drop", "price_drop_pct": 3.0,
        "owner_status": "owner_occupied", "distress_signals": "",
        "days_on_market": 120,
    })
    assert r["signal_type"] == "moderate_motivation", \
        f"DOM 120 should be moderate, got {r['signal_type']}"


def test_llm_pending_on_daily_429():
    """
    Fix 1: Daily 429 → returns 'pending' markers.
    Pending file is NOT saved (cache + inbox file design).
    Pending results NOT cached.
    """
    from llm_provider import classify_batch
    from pending_queue import pending_count, clear_pending
    from cache_manager import clear_cache, get_many
    import llm_provider

    clear_pending()
    clear_cache()

    daily_err = Exception(
        "429 RESOURCE_EXHAUSTED: GenerateRequestsPerDayPerProjectPerModel"
    )

    leads = [
        {"lead_id": i, "listing_type": "FSBO", "price_drop_pct": 10.0,
         "county": "Dallas", "owner_status": "owner_occupied",
         "distress_signals": "", "days_on_market": None, "property_type": ""}
        for i in range(3)
    ]

    call_count = {"n": 0}
    def fake_call(_prompt):
        call_count["n"] += 1
        raise daily_err

    with patch.object(llm_provider, "_call_gemini", side_effect=fake_call):
        results = classify_batch(leads)

    # Daily → 1 attempt only (no retry burn)
    assert call_count["n"] == 1, f"Expected 1 call, got {call_count['n']}"

    # All results should be "pending"
    pending_markers = sum(1 for r in results if r["signal_type"] == "pending")
    assert pending_markers == 3, f"Expected 3 pending markers, got {pending_markers}"

    # Fix 1: pending/ folder should be EMPTY (design change)
    assert pending_count() == 0, \
        f"Fix 1: pending/ should be empty (cache+inbox design), got {pending_count()}"

    # Pending results NOT cached
    cached, uncached = get_many(leads)
    assert len(cached) == 0, f"Pending leaked to cache: {len(cached)} hits"

    clear_pending()


# ============================================================
# TEST 7: END-TO-END
# ============================================================
def test_end_to_end_dry_run():
    """Full pipeline dry-run with mocked LLM."""
    import pandas as pd
    from data_collector import load_property_data
    from data_cleaner import (
        drop_invalid_rows, compute_price_drop_pct,
        detect_absentee_column, clean_phone_column,
    )
    import llm_provider

    csv_path = PROJECT_ROOT / "data" / "sample_30_leads.csv"
    assert csv_path.exists(), f"Sample CSV not found: {csv_path}"

    raw = load_property_data(str(csv_path))
    assert len(raw) == 30, f"Expected 30 rows, got {len(raw)}"

    df = drop_invalid_rows(raw)
    assert len(df) <= 30, "Drop did not reduce rows"
    assert len(df) > 0, "All rows dropped — sample data broken?"

    df = compute_price_drop_pct(df)
    df = detect_absentee_column(df)
    df = clean_phone_column(df)

    for col in ["price_drop_pct", "owner_status", "phone"]:
        assert col in df.columns, f"Missing column after cleaning: {col}"

    def fake_classify(leads):
        return [
            {"lead_id": l["lead_id"],
             "signal_type": "moderate_motivation",
             "reason": "smoke test mock"}
            for l in leads
        ]

    with patch.object(llm_provider, "classify_batch", side_effect=fake_classify):
        payload = [
            {"lead_id": int(i), "listing_type": str(r.get("listing_type", "")),
             "price_drop_pct": float(r.get("price_drop_pct", 0)),
             "county": str(r.get("county", "")),
             "owner_status": str(r.get("owner_status", "")),
             "distress_signals": str(r.get("distress_signals", "") or ""),
             "days_on_market": None, "property_type": ""}
            for i, r in df.iterrows()
        ]
        results = llm_provider.classify_batch(payload)

    assert len(results) == len(payload), \
        f"Result count mismatch: {len(results)} vs {len(payload)}"

    for r in results:
        assert "signal_type" in r
        assert "lead_id" in r


def test_output_contract():
    """
    Output columns match Module 3 contract.
    Fix 5: 9-column format (reason appended at end).
    """
    from data_cleaner import OUTPUT_COLUMNS

    expected = [
        "owner_name", "address", "county", "owner_status",
        "phone", "signal_type", "price", "date_flagged",
        "reason",  # Fix 5: AI reasoning exposed to client
    ]
    assert OUTPUT_COLUMNS == expected, \
        f"Output contract changed: {OUTPUT_COLUMNS}"

    # Fix 5: verify reason is LAST (backward-compat order)
    assert OUTPUT_COLUMNS[-1] == "reason", \
        "reason must be last column to preserve existing sheet layout"


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Voxel Estate Smoke Test")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show full output from each test")
    args = parser.parse_args()

    print("=" * 60)
    print("VOXEL ESTATE — SMOKE TEST")
    print("=" * 60)
    print(f"Root: {PROJECT_ROOT}")
    print(f"Verbose: {args.verbose}")
    print()
    print("Running tests (no real API calls)...")
    print()

    runner = TestRunner(verbose=args.verbose)

    print("[1] Imports")
    runner.run("Module imports", test_imports)

    print("\n[2] Adapters")
    runner.run("PropStream format", test_adapter_propstream)
    runner.run("BatchLeads format", test_adapter_batchleads)
    runner.run("Missing address → clear error", test_adapter_missing_address)

    print("\n[3] Cache")
    runner.run("Cache roundtrip", test_cache_roundtrip)
    runner.run("Distress invalidates cache key", test_cache_distress_invalidates)

    print("\n[4] Pending Queue")
    runner.run("Save/load/clear", test_pending_roundtrip)
    runner.run("Priority sort", test_pending_priority_sort)

    print("\n[5] Logger")
    runner.run("Trimmed traceback", test_logger_trimmed_traceback)

    print("\n[6] LLM Provider (mocked)")
    runner.run("Quota classifier", test_llm_quota_classifier)
    runner.run("Model-not-found classifier", test_llm_model_not_found_classifier)
    runner.run("Rule-based fallback", test_llm_rule_based_fallback)
    runner.run("Daily 429 → pending markers", test_llm_pending_on_daily_429)

    print("\n[7] End-to-End (mocked LLM)")
    runner.run("Full pipeline dry-run", test_end_to_end_dry_run)
    runner.run("Output contract", test_output_contract)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
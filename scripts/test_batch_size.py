"""
BATCH SIZE COMPARISON (Fix 9) — Hybrid Mock/Real
=================================================
Compares LLM_BATCH_SIZE=15 vs 30 on 100 leads.

MODES:
    Default:  Mock LLM (no API calls, runs anytime)
    --real:   Real Gemini API (needs quota; run when fresh)

METRICS:
    - API requests per 100 leads
    - JSON parse failures
    - Label agreement between runs
    - Average reasoning length

CRITICAL: Cache is CLEARED before each run.

USAGE:
    python scripts/test_batch_size.py                    # Mock (default)
    python scripts/test_batch_size.py --real             # Real API
"""

import sys
import os
import json
import re
import time
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv()


# ============================================================
# DATA LOADING
# ============================================================
def load_100_leads():
    from data_collector import load_property_data
    from data_cleaner import (
        drop_invalid_rows, compute_price_drop_pct,
        detect_absentee_column, clean_phone_column,
    )

    csv_path = PROJECT_ROOT / "data" / "sample_100_leads.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing: {csv_path}")

    raw = load_property_data(str(csv_path))
    df = drop_invalid_rows(raw)
    df = compute_price_drop_pct(df)
    df = detect_absentee_column(df)
    df = clean_phone_column(df)

    payload = []
    for idx, row in df.iterrows():
        payload.append({
            "lead_id": int(idx),
            "listing_type": str(row.get("listing_type", "unknown")),
            "price_drop_pct": float(row.get("price_drop_pct", 0)),
            "county": str(row.get("county", "unknown")),
            "owner_status": str(row.get("owner_status", "unknown")),
            "distress_signals": str(row.get("distress_signals", "") or ""),
            "days_on_market": None,
            "property_type": "",
        })
    return payload, len(df)


# ============================================================
# MOCK HELPERS
# ============================================================
def _extract_lead_ids(prompt: str):
    return [int(m) for m in re.findall(r"Lead #(\d+):", prompt)]


def _fake_response_for(prompt: str) -> str:
    lead_ids = _extract_lead_ids(prompt)
    results = [
        {
            "lead_id": lid_id,
            "signal_type": "moderate_motivation",
            "reason": "batch test mock — short reason",
        }
        for lid_id in lead_ids
    ]
    return json.dumps(results)


def _make_counting_mock():
    """
    Build a mock _call_gemini that increments _LLM_CALL_COUNT
    so get_llm_call_count() works in mock mode.
    """
    import llm_provider

    def counting_fake(prompt):
        llm_provider._LLM_CALL_COUNT += 1
        return _fake_response_for(prompt)

    return counting_fake


# ============================================================
# PATCH HELPERS
# ============================================================
def patch_obj(obj, attr_name, replacement):
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        original = getattr(obj, attr_name)
        setattr(obj, attr_name, replacement)
        try:
            yield
        finally:
            setattr(obj, attr_name, original)

    return _ctx()


def patch_sleep():
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        original = time.sleep
        time.sleep = lambda *a, **k: None
        try:
            yield
        finally:
            time.sleep = original

    return _ctx()


# ============================================================
# RUN ONE BATCH SIZE
# ============================================================
def run_with_batch_size(payload, batch_size, use_mock, label=""):
    import llm_provider
    from cache_manager import clear_cache

    clear_cache()
    llm_provider.reset_llm_call_count()

    original_batch = llm_provider.BATCH_SIZE
    llm_provider.BATCH_SIZE = batch_size

    print(f"\n[{label}] Batch size = {batch_size}")
    print("-" * 60)
    if use_mock:
        print("  Mode: MOCK (no real API calls)")

    json_failures = {"n": 0}
    original_parse = llm_provider._parse_json_response

    def tracking_parse(raw):
        try:
            return original_parse(raw)
        except Exception:
            json_failures["n"] += 1
            raise

    from contextlib import ExitStack
    try:
        with ExitStack() as stack:
            stack.enter_context(
                patch_obj(llm_provider, "_parse_json_response", tracking_parse)
            )
            stack.enter_context(patch_sleep())

            if use_mock:
                # Mock with counter increment
                stack.enter_context(
                    patch_obj(llm_provider, "_call_gemini",
                              _make_counting_mock())
                )

            start = time.time()
            results = llm_provider.classify_batch(payload)
            duration = time.time() - start
    finally:
        llm_provider.BATCH_SIZE = original_batch

    llm_calls = llm_provider.get_llm_call_count()
    pending = sum(1 for r in results if r.get("signal_type") == "pending")
    fallback = sum(1 for r in results if "Rule-based" in r.get("reason", ""))
    reason_lengths = [len(r.get("reason", "")) for r in results]
    avg_reason_len = (sum(reason_lengths) / len(reason_lengths)
                      if reason_lengths else 0.0)

    return {
        "batch_size": batch_size,
        "duration": duration,
        "llm_calls": llm_calls,
        "pending": pending,
        "fallback": fallback,
        "json_failures": json_failures["n"],
        "avg_reason_len": avg_reason_len,
        "results": results,
    }


# ============================================================
# COMPARE
# ============================================================
def compare_labels(results_a, results_b):
    map_a = {r["lead_id"]: r["signal_type"] for r in results_a}
    map_b = {r["lead_id"]: r["signal_type"] for r in results_b}

    common_ids = set(map_a.keys()) & set(map_b.keys())
    if not common_ids:
        return 0, 0, 0.0

    matches = sum(1 for lid in common_ids if map_a[lid] == map_b[lid])
    return matches, len(common_ids), (matches / len(common_ids) * 100)


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-a", type=int, default=15)
    parser.add_argument("--size-b", type=int, default=30)
    parser.add_argument("--real", action="store_true",
                        help="Use real Gemini API (needs quota)")
    args = parser.parse_args()

    use_mock = not args.real

    print("=" * 70)
    print("  BATCH SIZE COMPARISON (Fix 9)")
    print("=" * 70)
    print(f"  Mode:        {'REAL API' if args.real else 'MOCK (no API)'}")
    print(f"  Size A:      {args.size_a}")
    print(f"  Size B:      {args.size_b}")

    # ---- Load ----
    print(f"\n[1/4] Loading 100 leads...")
    payload, n = load_100_leads()
    print(f"      Valid rows: {n}")

    # ---- Run A ----
    print(f"\n[2/4] Running with batch_size={args.size_a}...")
    stat_a = run_with_batch_size(payload, args.size_a, use_mock, label="RUN A")

    # ---- Run B ----
    print(f"\n[3/4] Running with batch_size={args.size_b}...")
    stat_b = run_with_batch_size(payload, args.size_b, use_mock, label="RUN B")

    # ---- Compare ----
    print(f"\n[4/4] Comparing results...")
    matches, total, pct = compare_labels(stat_a["results"], stat_b["results"])

    # ---- Report ----
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    col_a = f"Size {args.size_a}"
    col_b = f"Size {args.size_b}"
    print(f"  {'Metric':<25} {col_a:<18} {col_b:<18}")
    print(f"  {'-'*25} {'-'*18} {'-'*18}")
    print(f"  {'Batch size':<25} {stat_a['batch_size']:<18} {stat_b['batch_size']:<18}")
    print(f"  {'Duration (sec)':<25} {stat_a['duration']:<18.2f} {stat_b['duration']:<18.2f}")
    print(f"  {'LLM calls':<25} {stat_a['llm_calls']:<18} {stat_b['llm_calls']:<18}")
    print(f"  {'Pending rows':<25} {stat_a['pending']:<18} {stat_b['pending']:<18}")
    print(f"  {'Fallback rows':<25} {stat_a['fallback']:<18} {stat_b['fallback']:<18}")
    print(f"  {'JSON failures':<25} {stat_a['json_failures']:<18} {stat_b['json_failures']:<18}")
    print(f"  {'Avg reason len':<25} {stat_a['avg_reason_len']:<18.1f} {stat_b['avg_reason_len']:<18.1f}")
    print()
    print(f"  Label agreement: {matches}/{total} ({pct:.1f}%)")

    expected_a = (n + args.size_a - 1) // args.size_a
    expected_b = (n + args.size_b - 1) // args.size_b
    print()
    print(f"  Expected LLM calls: A={expected_a}, B={expected_b}")

    # ---- Verdict ----
    print("\n" + "=" * 70)
    # Verdict only makes sense if calls > 0
    if stat_a["llm_calls"] == 0 and stat_b["llm_calls"] == 0:
        verdict = "SKIPPED — no API calls made (check mode)"
    elif (pct >= 95 and stat_b["llm_calls"] < stat_a["llm_calls"]
            and stat_b["json_failures"] <= stat_a["json_failures"]):
        verdict = (f"GO — batch={args.size_b} works: "
                   f"{stat_b['llm_calls']} calls vs {stat_a['llm_calls']}, "
                   f"same labels")
    elif pct >= 95:
        verdict = f"OK — labels match but no call savings with batch={args.size_b}"
    elif pct >= 85:
        verdict = "MODERATE — some label drift"
    else:
        verdict = f"POOR — batch={args.size_b} breaks label quality"
    print(f"  VERDICT: {verdict}")
    print("=" * 70)

    # ---- Assertions (only meaningful when calls made) ----
    assert stat_a["avg_reason_len"] <= 250, "FAIL: reason too long (>250)"
    assert stat_b["avg_reason_len"] <= 250, "FAIL: reason too long (>250)"

    # Real-mode: skip strict call-count assertion (quota may abort)
    if use_mock:
        assert stat_a["llm_calls"] == expected_a, \
            f"FAIL: A expected {expected_a}, got {stat_a['llm_calls']}"
        assert stat_b["llm_calls"] == expected_b, \
            f"FAIL: B expected {expected_b}, got {stat_b['llm_calls']}"
        assert pct == 100.0, \
            f"FAIL: mock label agreement {pct}% — expected 100%"
    else:
        # Real mode: if no quota hit, calls should match
        if stat_a["pending"] == 0:
            assert stat_a["llm_calls"] == expected_a, \
                f"FAIL: A expected {expected_a}, got {stat_a['llm_calls']}"
        else:
            print(f"  ⚠ Run A had {stat_a['pending']} pending — "
                  f"quota likely hit, skipping call-count assertion")
        if stat_b["pending"] == 0:
            assert stat_b["llm_calls"] == expected_b, \
                f"FAIL: B expected {expected_b}, got {stat_b['llm_calls']}"
        else:
            print(f"  ⚠ Run B had {stat_b['pending']} pending — "
                  f"quota likely hit, skipping call-count assertion")

    print()
    print("  ✅ PASS: Batch comparison complete")
    if use_mock:
        print("     (mock mode — for real numbers, run with --real)")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
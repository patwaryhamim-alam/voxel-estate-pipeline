"""
Module 2: AI Cleaning
Takes Module 1's raw DataFrame and returns a clean, classified DataFrame.

DESIGN:
    - Python does deterministic work (filter, math, absentee detection)
    - LLM provider does judgment (motivation classification)
    - Results mapped back via lead_id (never send PII to AI)
    - Optional RunSummary tracking for pipeline reporting
    - v5: sends days_on_market + property_type to AI
    - v6b: safe column access for detail_df
    - v6c (Fix 1): returns partial_count in detail for run summary
    - v6d (Fix 1): AI request count approximation for partial runs
    - v7 (Fix 2): priority sort BEFORE batching
    - v8 (Fix 5): AI reasoning delivered to Sheet (9th column)
"""

import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

import warnings
warnings.filterwarnings("ignore")

import json
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

from data_collector import load_property_data
from absentee_detector import detect_absentee
from us_validators import validate_phone, format_phone
from llm_provider import classify_batch

load_dotenv()


# ============================================================
# OUTPUT CONTRACT — Module 3 expects these columns
# ============================================================
# Fix 5: "reason" appended at END (preserves 8-col layout for
# existing sheets; new column auto-added to header by sheet_pusher)
OUTPUT_COLUMNS = [
    "owner_name",
    "address",
    "county",
    "owner_status",
    "phone",
    "signal_type",
    "price",
    "date_flagged",
    "reason",           # Fix 5: AI reasoning exposed to client
]

REASON_MAX_LEN = 250    # Fix 5: cap for readability


# ============================================================
# STEP 1: Drop invalid rows
# ============================================================
def drop_invalid_rows(df):
    before = len(df)
    df = df.dropna(subset=["owner_name", "address"]).copy()
    df = df[df["owner_name"].astype(str).str.strip() != ""]
    df = df[df["address"].astype(str).str.strip() != ""]
    after = len(df)
    print(f"[Python] Dropped {before - after} invalid rows ({before} → {after})")
    return df.reset_index(drop=True)


# ============================================================
# STEP 2: Compute price drop %
# ============================================================
def compute_price_drop_pct(df):
    def _pct(row):
        try:
            prev = float(row["previous_price"])
            curr = float(row["list_price"])
            if prev <= 0:
                return 0.0
            return round((prev - curr) / prev * 100, 1)
        except (ValueError, TypeError):
            return 0.0

    df["price_drop_pct"] = df.apply(_pct, axis=1)
    return df


# ============================================================
# STEP 3: Absentee detection
# ============================================================
def detect_absentee_column(df):
    statuses = []
    for _, row in df.iterrows():
        status, _ = detect_absentee(
            row.get("address"),
            row.get("owner_mailing_address"),
            owner_name=row.get("owner_name"),
        )
        statuses.append(status)
    df["owner_status"] = statuses
    return df


# ============================================================
# STEP 4: Phone validation + cleaning
# ============================================================
def clean_phone_column(df):
    if "phone" not in df.columns:
        df["phone"] = None
        return df

    cleaned = []
    for phone in df["phone"]:
        ok, digits, _ = validate_phone(phone)
        if ok:
            cleaned.append(format_phone(digits))
        else:
            cleaned.append(None)
    df["phone"] = cleaned
    return df


# ============================================================
# STEP 5: Safe int converter
# ============================================================
def _safe_int_or_none(val):
    """Convert to int, return None if invalid."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


# ============================================================
# PRIORITY SCORING (Fix 2)
# ============================================================
def _lead_priority(row) -> float:
    """Score for batching. Higher = process first."""
    try:
        distress = str(row.get("distress_signals", "") or "").lower()
        owner = str(row.get("owner_status", "") or "").lower()
        drop = float(row.get("price_drop_pct", 0) or 0)
    except (ValueError, TypeError):
        return 0.0

    score = 0.0
    if distress and distress != "none":
        score += 100
    if "out_of_state_absentee" in owner:
        score += 50
    elif "in_state_absentee" in owner:
        score += 25
    score += min(max(drop, 0.0), 20.0)
    return score


def _sort_by_priority(df):
    """Return a copy of df sorted by priority (descending)."""
    if "_priority" not in df.columns:
        df = df.copy()
        df["_priority"] = df.apply(_lead_priority, axis=1)
    return df.sort_values("_priority", ascending=False, kind="stable")


# ============================================================
# STEP 6: AI classification
# ============================================================
def classify_leads_with_provider(df, summary=None):
    """
    Send PII-free lead data to LLM provider.
    Map results back via lead_id.
    Fix 2: sorted by priority before batching.
    """
    df = df.copy()
    df["_priority"] = df.apply(_lead_priority, axis=1)
    df_sorted = df.sort_values("_priority", ascending=False, kind="stable")

    top_n = min(3, len(df_sorted))
    if top_n > 0:
        top_scores = df_sorted["_priority"].head(top_n).tolist()
        print(f"[Priority] Sorted {len(df_sorted)} leads — "
              f"top {top_n} scores: {[round(s,1) for s in top_scores]}")

    payload = []
    for idx, row in df_sorted.iterrows():
        payload.append({
            "lead_id": int(idx),
            "listing_type": str(row.get("listing_type", "unknown")),
            "price_drop_pct": float(row.get("price_drop_pct", 0)),
            "county": str(row.get("county", "unknown")),
            "owner_status": str(row.get("owner_status", "unknown")),
            "distress_signals": str(row.get("distress_signals", "") or ""),
            "days_on_market": _safe_int_or_none(row.get("days_on_market")),
            "property_type": str(row.get("property_type", "") or ""),
        })

    print(f"[AI] Sending {len(payload)} leads (batch mode, no PII)...")

    cache_before = _get_cache_stats_safe()
    results = classify_batch(payload)
    cache_after = _get_cache_stats_safe()

    result_map = {r["lead_id"]: r for r in results}

    signal_types = []
    ai_reasons = []
    partial_count = 0
    cached_count = 0

    for idx in df.index:
        r = result_map.get(int(idx), {})
        st = r.get("signal_type", "unclassified")
        if st == "pending":
            partial_count += 1
        if r.get("from_cache"):
            cached_count += 1
        signal_types.append(st)
        ai_reasons.append(r.get("reason", ""))

    df["signal_type"] = signal_types
    df["ai_reason"] = ai_reasons
    df.drop(columns=["_priority"], inplace=True)

    df.attrs["partial_count"] = partial_count
    if partial_count > 0:
        print(f"[AI] Partial: {len(payload) - partial_count}/{len(payload)} "
              f"classified ({partial_count} pending)")
        try:
            from logger import get_logger
            get_logger(__name__).warning(
                f"Partial run: {partial_count}/{len(payload)} leads pending"
            )
        except Exception:
            pass

    if summary is not None:
        try:
            newly_cached = max(0, cache_after - cache_before)
            cached_hits = cached_count if cached_count > 0 else max(
                0, len(payload) - newly_cached - partial_count
            )
            attempted = len(payload) - cached_hits
            approx_requests = 0
            if attempted > 0:
                try:
                    from llm_provider import BATCH_SIZE
                    approx_requests = (attempted + BATCH_SIZE - 1) // BATCH_SIZE
                except Exception:
                    approx_requests = 1
            summary.set_ai_stats(
                requests=approx_requests,
                cached=cached_hits,
                classified=len(payload) - partial_count,
                fallback=0,
            )
            if hasattr(summary, "set_partial_count"):
                summary.set_partial_count(partial_count)
        except Exception:
            pass

    return df


def _get_cache_stats_safe():
    try:
        from cache_manager import cache_stats
        return cache_stats().get("total_cached", 0)
    except Exception:
        return 0


# ============================================================
# MAIN: clean_leads()
# ============================================================
def clean_leads(df, summary=None):
    """Clean and classify leads. Returns (clean_output_df, detail_df)."""
    print("=" * 60)
    print("MODULE 2: AI CLEANING")
    print("=" * 60)
    print(f"Input rows: {len(df)}")

    if summary is not None:
        summary.set_input_rows(len(df))

    before_filter = len(df)
    df = drop_invalid_rows(df)
    dropped = before_filter - len(df)

    if summary is not None:
        summary.set_dropped_rows(dropped)

    df = compute_price_drop_pct(df)
    df = detect_absentee_column(df)
    df = clean_phone_column(df)

    df = classify_leads_with_provider(df, summary=summary)

    df["price"] = df["list_price"]
    df["date_flagged"] = datetime.now().strftime("%Y-%m-%d")

    # Fix 5: expose AI reasoning as "reason" column (capped length)
    df["reason"] = (
        df["ai_reason"]
        .fillna("")
        .astype(str)
        .str.slice(0, REASON_MAX_LEN)
    )

    output = df[OUTPUT_COLUMNS].copy()

    detail_candidates = [
        "owner_name", "owner_status", "phone",
        "signal_type", "ai_reason", "price_drop_pct",
        "days_on_market", "property_type",
    ]
    detail_cols = [c for c in detail_candidates if c in df.columns]
    detail = df[detail_cols].copy()
    detail.attrs["partial_count"] = df.attrs.get("partial_count", 0)

    return output, detail


# ============================================================
# PRESENTATION
# ============================================================
def print_before_after(raw_df, clean_df, detail_df):
    print("\n" + "=" * 60)
    print("AI CLASSIFICATION DETAIL:")
    print("=" * 60)
    print(detail_df.to_string(index=False))
    print("\n" + "=" * 60)
    print("AFTER (clean output for Module 3):")
    print("=" * 60)
    print(clean_df.to_string(index=False))


def main():
    try:
        raw_df = load_property_data()
        clean_df, detail_df = clean_leads(raw_df)
        print_before_after(raw_df, clean_df, detail_df)
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
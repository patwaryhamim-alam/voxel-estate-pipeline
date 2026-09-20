"""
Module 2: AI Cleaning
Takes Module 1's raw DataFrame and returns a clean, classified DataFrame.

DESIGN:
    - Python does deterministic work (filter, math, absentee detection)
    - LLM provider does judgment (motivation classification)
    - Results mapped back via lead_id (never send PII to AI)
    - Optional RunSummary tracking for pipeline reporting
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
OUTPUT_COLUMNS = [
    "owner_name",
    "address",
    "county",
    "owner_status",
    "phone",
    "signal_type",
    "price",
    "date_flagged",
]


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
            owner_name=row.get("owner_name"),  # For LLC/Trust detection
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
# STEP 5: AI classification (via LLM provider abstraction)
# ============================================================
def classify_leads_with_provider(df, summary=None):
    """
    Send PII-free lead data to LLM provider.
    Map results back via lead_id.
    Optionally track stats in RunSummary.
    """
    # Build PII-free payload (includes distress_signals)
    payload = []
    for idx, row in df.iterrows():
        payload.append({
            "lead_id": int(idx),
            "listing_type": str(row.get("listing_type", "unknown")),
            "price_drop_pct": float(row.get("price_drop_pct", 0)),
            "county": str(row.get("county", "unknown")),
            "owner_status": str(row.get("owner_status", "unknown")),
            "distress_signals": str(row.get("distress_signals", "") or ""),
        })

    print(f"[AI] Sending {len(payload)} leads (batch mode, no PII)...")

    # Track cache stats before/after
    cache_before = _get_cache_stats_safe()

    # Call provider (handles batching, retry, fallback internally)
    results = classify_batch(payload)

    cache_after = _get_cache_stats_safe()

    # Map back by lead_id
    result_map = {r["lead_id"]: r for r in results}

    signal_types = []
    ai_reasons = []
    for idx in df.index:
        r = result_map.get(int(idx), {})
        signal_types.append(r.get("signal_type", "unclassified"))
        ai_reasons.append(r.get("reason", ""))

    df["signal_type"] = signal_types
    df["ai_reason"] = ai_reasons

    # Update summary
    if summary is not None:
        try:
            newly_cached = max(0, cache_after - cache_before)
            cached_hits = len(payload) - newly_cached
            summary.set_ai_stats(
                requests=0,  # approximate (batched internally)
                cached=cached_hits,
                classified=len(payload),
                fallback=0,  # tracked inside llm_provider
            )
        except Exception:
            pass

    return df


def _get_cache_stats_safe():
    """Safely get total cached count."""
    try:
        from cache_manager import cache_stats
        return cache_stats().get("total_cached", 0)
    except Exception:
        return 0


# ============================================================
# MAIN: clean_leads()
# ============================================================
def clean_leads(df, summary=None):
    """
    Clean and classify leads.

    Args:
        df: Raw DataFrame from Module 1
        summary: Optional RunSummary object for tracking

    Returns:
        (clean_output_df, detail_df)
    """
    print("=" * 60)
    print("MODULE 2: AI CLEANING")
    print("=" * 60)
    print(f"Input rows: {len(df)}")

    if summary is not None:
        summary.set_input_rows(len(df))

    # Python steps
    before_filter = len(df)
    df = drop_invalid_rows(df)
    dropped = before_filter - len(df)

    if summary is not None:
        summary.set_dropped_rows(dropped)

    df = compute_price_drop_pct(df)
    df = detect_absentee_column(df)
    df = clean_phone_column(df)

    # AI step
    df = classify_leads_with_provider(df, summary=summary)

    # Final columns
    df["price"] = df["list_price"]
    df["date_flagged"] = datetime.now().strftime("%Y-%m-%d")

    # Output
    output = df[OUTPUT_COLUMNS].copy()
    detail = df[["owner_name", "owner_status", "phone", "signal_type", "ai_reason", "price_drop_pct"]]
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
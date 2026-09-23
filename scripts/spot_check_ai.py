"""
SPOT CHECK v3 — Real AI Accuracy Test (with Days/Type)

FIX 1 + FIX 5:
    - Uses sample_100_leads.csv
    - Clears cache first
    - Reports llm_calls count (must be > 0)
    - Shows: features → AI label → reasoning → rule label
    - Highlights disagreements
    - Shows days_on_market + property_type in features
    - Covers edge cases

USAGE:
    python scripts/spot_check_ai.py
    python scripts/spot_check_ai.py --sample 30 --csv data/sample_100_leads.csv
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
from dotenv import load_dotenv

from data_collector import load_property_data
from data_cleaner import (
    drop_invalid_rows,
    compute_price_drop_pct,
    detect_absentee_column,
    clean_phone_column,
    classify_leads_with_provider,
)
from cache_manager import clear_cache, cache_stats
from llm_provider import get_llm_call_count, reset_llm_call_count

load_dotenv()


# ============================================================
# RULE-BASED EXPECTED LABEL
# ============================================================
def expected_label(row):
    """What the label should be based on rules."""
    try:
        drop = float(row.get("price_drop_pct", 0) or 0)
    except (ValueError, TypeError):
        drop = 0.0

    ltype = str(row.get("listing_type", "")).lower()
    owner = str(row.get("owner_status", "")).lower()
    distress = str(row.get("distress_signals", "") or "").lower()

    is_business = "llc_or_trust_owner" in owner
    owner_effective = "unknown" if is_business else owner

    high_distress = any(s in distress for s in
                        ["tax_delinquent", "pre_foreclosure", "vacant"])
    medium_distress = any(s in distress for s in
                          ["expired_listing", "divorce", "probate"])

    # Fix 5: days_on_market in rules
    dom_raw = row.get("days_on_market")
    try:
        dom = int(float(dom_raw)) if dom_raw is not None and not pd.isna(dom_raw) else None
    except (ValueError, TypeError):
        dom = None

    if (drop > 10 or (ltype == "fsbo" and drop > 5)
            or owner_effective == "out_of_state_absentee"
            or high_distress):
        return "high_motivation"
    elif (drop > 5 or ltype == "fsbo"
          or owner_effective == "in_state_absentee"
          or medium_distress
          or (dom is not None and dom > 90)):
        return "moderate_motivation"
    else:
        return "low_motivation"


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/sample_100_leads.csv")
    parser.add_argument("--sample", type=int, default=30)
    args = parser.parse_args()

    print("=" * 80)
    print("  SPOT CHECK v3 — Real AI Accuracy Test (with Days/Type)")
    print("=" * 80)
    print(f"  CSV: {args.csv}")
    print(f"  Sample: {args.sample} leads")
    print()

    # ---- STEP 1: Clear cache ----
    print("[1/5] Clearing cache for fresh test...")
    cleared = clear_cache()
    print(f"      Removed {cleared} cached entries")
    reset_llm_call_count()

    # ---- STEP 2: Load CSV ----
    print("[2/5] Loading CSV...")
    raw = load_property_data(args.csv)
    print(f"      Loaded {len(raw)} rows")

    # ---- STEP 3: Clean (Python) ----
    print("[3/5] Cleaning (Python steps)...")
    df = drop_invalid_rows(raw)
    df = compute_price_drop_pct(df)
    df = detect_absentee_column(df)
    df = clean_phone_column(df)
    df["expected_by_rules"] = df.apply(expected_label, axis=1)
    print(f"      Valid rows: {len(df)}")

    # ---- STEP 4: AI classification ----
    print("[4/5] Running AI classification...")
    df = classify_leads_with_provider(df)
    df["match"] = df["signal_type"] == df["expected_by_rules"]

    # ---- STEP 5: Report ----
    print("[5/5] Generating report...")

    sample = df.head(args.sample).copy()
    matched = int(sample["match"].sum())
    total = len(sample)
    match_pct = (matched / total * 100) if total > 0 else 0
    disagreements = sample[~sample["match"]]

    lines = []
    lines.append("=" * 80)
    lines.append("  SPOT CHECK REPORT v3")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  CSV: {args.csv}")
    lines.append(f"  Reviewed: {len(sample)} leads")
    lines.append("=" * 80)
    lines.append("")

    for i, (idx, row) in enumerate(sample.iterrows(), 1):
        tag = "[MATCH]" if row["match"] else "[DIFF ]"

        # Fix 5: include days_on_market + property_type in features
        dom = row.get("days_on_market")
        dom_str = f"{int(dom)}d" if dom is not None and not pd.isna(dom) else "?"

        ptype = row.get("property_type") or "?"

        feat = (
            f"type={row.get('listing_type', '?')}, "
            f"drop={row.get('price_drop_pct', 0)}%, "
            f"owner={row.get('owner_status', '?')}, "
            f"distress={row.get('distress_signals', '') or 'none'}, "
            f"dom={dom_str}, "
            f"ptype={ptype}"
        )

        lines.append("-" * 80)
        lines.append(f"[{i}] {tag} | {row.get('owner_name', 'unknown')}")
        lines.append(f"    Features:      {feat}")
        lines.append(f"    AI Label:      {row.get('signal_type', 'unknown')}")
        lines.append(f"    AI Reasoning:  {str(row.get('ai_reason', ''))[:160]}")
        lines.append(f"    Rule Label:    {row.get('expected_by_rules', 'unknown')}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("  SUMMARY")
    lines.append("=" * 80)
    lines.append(f"  LLM calls made:       {get_llm_call_count()}")
    lines.append(f"  Cache hits:           {total - get_llm_call_count()}")
    lines.append(f"  Total reviewed:       {total}")
    lines.append(f"  Matched rules:        {matched}")
    lines.append(f"  Differed:             {total - matched}")
    lines.append(f"  Match rate:           {match_pct:.1f}%")
    lines.append("")

    lines.append("  AI Label Distribution:")
    for label, count in sample["signal_type"].value_counts().items():
        lines.append(f"    {label}: {count}")
    lines.append("")

    if len(disagreements) > 0:
        lines.append("  DISAGREEMENTS (AI vs Rules):")
        for i, (idx, row) in enumerate(disagreements.iterrows(), 1):
            lines.append(
                f"    [{i}] {row.get('owner_name', 'unknown')} — "
                f"AI={row['signal_type']} | Rule={row['expected_by_rules']}"
            )
        lines.append("")

    llm_calls = get_llm_call_count()
    if llm_calls == 0:
        verdict = "INVALID — 0 LLM calls (cache was not cleared?)"
    elif match_pct >= 80:
        verdict = "GOOD — AI is accurate. Pilot-safe."
    elif match_pct >= 60:
        verdict = "MODERATE — Review disagreements above."
    else:
        verdict = "POOR — Do NOT pilot. Fix prompt first."
    lines.append(f"  VERDICT: {verdict}")
    lines.append("=" * 80)

    report_text = "\n".join(lines)
    print()
    print(report_text)

    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    report_path = output_dir / f"spot_check_{ts}.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()
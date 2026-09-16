"""
Module 2: AI Cleaning
Takes Module 1's raw DataFrame and returns a clean, classified DataFrame.
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
from langchain_google_genai import ChatGoogleGenerativeAI

from data_collector import load_property_data
from absentee_detector import detect_absentee
from us_validators import validate_phone, format_phone

load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# OUTPUT CONTRACT — Module 3 expects these columns
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
    return df


# ============================================================
# STEP 2: Compute price drop %
# ============================================================
def compute_price_drop_pct(df):
    df["price_drop_pct"] = (
        (df["previous_price"] - df["list_price"]) / df["previous_price"] * 100
    ).round(1)
    return df


# ============================================================
# STEP 3: Absentee detection
# ============================================================
def detect_absentee_column(df):
    """Add 'owner_status' column based on property vs mailing address."""
    statuses = []
    for _, row in df.iterrows():
        status, _ = detect_absentee(
            row.get("address"),
            row.get("owner_mailing_address"),
        )
        statuses.append(status)
    df["owner_status"] = statuses
    return df


# ============================================================
# STEP 3B: Phone validation + cleaning
# ============================================================
def clean_phone_column(df):
    """Validate and format US phone numbers as (XXX) XXX-XXXX."""
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
# STEP 4: AI classification
# ============================================================
def build_ai_prompt(df):
    leads_block = ""
    for idx, row in df.iterrows():
        leads_block += f"""
Lead #{idx + 1}:
- Owner: {row['owner_name']}
- Address: {row['address']}
- County: {row['county']}
- Listing Type: {row['listing_type']}
- List Price: ${row['list_price']}
- Previous Price: ${row['previous_price']}
- Price Drop: {row['price_drop_pct']}%
- Owner Status: {row['owner_status']}
"""

    prompt = f"""You are a US real estate lead analyst.

{leads_block}

For each lead, classify motivation and give a short reason.

CLASSIFICATION RULES:
- "high_motivation"   = price drop > 10% OR (FSBO and price drop > 5%) OR out_of_state_absentee
- "moderate_motivation" = FSBO with price drop 0-10%, OR price drop 5-10%, OR in_state_absentee
- "low_motivation"    = no significant signals AND owner_occupied

PRIORITY BONUS (add to reasoning):
- out_of_state_absentee is the STRONGEST motivation signal — always mention it
- in_state_absentee is a moderate signal

Return ONLY a JSON array, one object per lead, in order:
[
  {{"lead_number": 1, "signal_type": "high_motivation", "reason": "15% price drop + out-of-state owner"}},
  {{"lead_number": 2, "signal_type": "moderate_motivation", "reason": "FSBO, owner-occupied"}}
]

No extra text. Only JSON.
"""
    return prompt


def classify_with_ai(df):
    prompt = build_ai_prompt(df)
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )
    response = llm.invoke(prompt)
    raw = response.text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


# ============================================================
# MAIN
# ============================================================
def clean_leads(df):
    print("=" * 60)
    print("MODULE 2: AI CLEANING")
    print("=" * 60)
    print(f"Input rows: {len(df)}")

    df = drop_invalid_rows(df)
    df = compute_price_drop_pct(df)
    df = detect_absentee_column(df)
    df = clean_phone_column(df)
    df = df.reset_index(drop=True)

    print(f"[AI] Sending {len(df)} leads to {MODEL_NAME}...")
    ai_results = classify_with_ai(df)

    df["signal_type"] = [r["signal_type"] for r in ai_results]
    df["ai_reason"] = [r["reason"] for r in ai_results]
    df["price"] = df["list_price"]
    df["date_flagged"] = datetime.now().strftime("%Y-%m-%d")

    output = df[OUTPUT_COLUMNS].copy()
    detail = df[["owner_name", "owner_status", "phone", "signal_type", "ai_reason", "price_drop_pct"]]
    return output, detail


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
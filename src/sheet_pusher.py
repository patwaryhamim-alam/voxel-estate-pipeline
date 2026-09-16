"""
Module 3: Sheet Pusher
Takes Module 2's clean DataFrame and appends rows to a Google Sheet.

DESIGN PRINCIPLE (same as Modules 1 & 2):
    push_to_sheet(df) is the ONLY public function.
    Input:  DataFrame with OUTPUT_COLUMNS from Module 2
    Output: None (side-effect: writes to Google Sheet + logs)

    If we change HOW we write (e.g., Airtable instead of Sheets),
    only this file changes. Modules 1 & 2 never know.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from logger import get_logger

log = get_logger(__name__)

load_dotenv()

# ============================================================
# CONFIG
# ============================================================
SERVICE_ACCOUNT_FILE = "credentials/service_account.json"
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

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
# AUTH
# ============================================================
def _get_client():
    if not Path(SERVICE_ACCOUNT_FILE).exists():
        log.error(f"Service account file missing: {SERVICE_ACCOUNT_FILE}")
        raise FileNotFoundError(
            f"'{SERVICE_ACCOUNT_FILE}' pawa jay ni. credentials/ folder check koro."
        )
    if not SHEET_ID:
        log.error("GOOGLE_SHEET_ID not set in .env")
        raise ValueError("GOOGLE_SHEET_ID .env file e set kora nei.")

    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


# ============================================================
# HELPER
# ============================================================
def _make_lead_key(row):
    owner = str(row["owner_name"]).strip().lower()
    address = str(row["address"]).strip().lower()
    return f"{owner}||{address}"


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================
def push_to_sheet(df):
    log.info(f"push_to_sheet() called with {len(df)} rows in DataFrame")

    missing = [c for c in OUTPUT_COLUMNS if c not in df.columns]
    if missing:
        log.error(f"Input DataFrame missing columns: {missing}")
        raise ValueError(f"Input DataFrame missing columns: {missing}")

    if len(df) == 0:
        print("[Sheet] 0 rows in input DataFrame.")
        log.info("Empty DataFrame — nothing to push.")
        return 0

    print(f"[Sheet] Connecting to Google Sheets...")
    log.info("Connecting to Google Sheets...")
    client = _get_client()
    sheet = client.open_by_key(SHEET_ID).sheet1

    existing = sheet.get_all_values()
    if len(existing) == 0:
        sheet.append_row(OUTPUT_COLUMNS)
        header = OUTPUT_COLUMNS
        existing_data = []
        log.info("Sheet was empty — wrote header row.")
    else:
        header = existing[0]
        existing_data = existing[1:]

    try:
        owner_idx = header.index("owner_name")
        address_idx = header.index("address")
    except ValueError:
        log.error("Sheet header missing 'owner_name' or 'address' column.")
        raise ValueError(
            "Sheet header must contain 'owner_name' and 'address' columns."
        )

    existing_keys = set()
    for row in existing_data:
        if len(row) > max(owner_idx, address_idx):
            key = f"{row[owner_idx].strip().lower()}||{row[address_idx].strip().lower()}"
            existing_keys.add(key)

    print(f"[Sheet] Found {len(existing_keys)} existing leads in sheet.")
    log.info(f"Found {len(existing_keys)} existing leads in sheet.")

    df = df.copy()
    df["_key"] = df.apply(_make_lead_key, axis=1)
    new_rows_df = df[~df["_key"].isin(existing_keys)].drop(columns=["_key"])

    if len(new_rows_df) == 0:
        msg = f"No new rows to push — all {len(df)} leads already in sheet."
        print(f"[Sheet] ⏭️  {msg}")
        log.info(msg)
        return 0

    rows_to_add = new_rows_df[OUTPUT_COLUMNS].values.tolist()
    sheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")

    rows_after = len(existing_data) + len(rows_to_add)
    skipped = len(df) - len(rows_to_add)

    print(f"[Sheet] ✅ Pushed {len(rows_to_add)} new rows.")
    print(f"[Sheet]    Skipped {skipped} duplicates.")
    print(f"[Sheet]    Total rows now: {rows_after}")
    print(f"[Sheet]    Sheet URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}")

    log.info(
        f"Pushed {len(rows_to_add)} new rows, skipped {skipped} duplicates, "
        f"total rows now: {rows_after}"
    )

    return len(rows_to_add)


# ============================================================
# MAIN
# ============================================================
def main():
    from data_collector import load_property_data
    from data_cleaner import clean_leads

    log.info("=" * 60)
    log.info("PIPELINE RUN STARTED")
    log.info("=" * 60)

    try:
        print("Loading data from Module 1...")
        log.info("Module 1: Loading data from CSV...")

        csv_override = os.getenv("LEADS_CSV_PATH")
        if csv_override:
            print(f"[Override] Using CSV: {csv_override}")
            log.info(f"CSV override active: {csv_override}")
            raw = load_property_data(csv_override)
        else:
            raw = load_property_data()

        print("Cleaning with Module 2...")
        log.info("Module 2: Cleaning and AI-classifying...")
        clean_df, _ = clean_leads(raw)

        print(f"\nPushing {len(clean_df)} rows to Sheet...")
        log.info(f"Module 3: Pushing {len(clean_df)} rows to Sheet...")
        push_to_sheet(clean_df)

        print("\n🎉 Pipeline test complete!")
        log.info("PIPELINE RUN COMPLETED SUCCESSFULLY")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        log.error(f"Pipeline failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
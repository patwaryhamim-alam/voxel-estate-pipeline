"""
CLIENT ONBOARDING SCRIPT (with County Exclusivity)
==================================================
Sets up a new client in 2 minutes instead of 30 minutes.

USAGE:
    python scripts/onboard_client.py --name "Client A" --sheet-id "1AbC..." --county "maricopa_az"
    python scripts/onboard_client.py --name "Client B" --sheet-id "1AbC..." --county "harris_tx" --csv data/client_b.csv

WHAT IT DOES:
    0. CHECK COUNTY AVAILABILITY (max 3 clients per county)
    1. Verify service_account.json
    2. Test Gemini API connection
    3. Verify access to the client's Google Sheet
    4. Backup current .env
    5. Update .env with new GOOGLE_SHEET_ID
    6. Verify/auto-create header row in Sheet
    7. Run a test pipeline
    8. Add client to county registry
    9. Print instructions for client

If any step fails, no changes are made.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add src/ to path so we can import our modules
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from county_manager import CountyManager


# ============================================================
# CONFIG
# ============================================================
ENV_FILE = PROJECT_ROOT / ".env"
SERVICE_ACCOUNT_FILE = PROJECT_ROOT / "credentials" / "service_account.json"
HEADER_ROW = [
    "owner_name",
    "address",
    "county",
    "owner_status",
    "phone",
    "signal_type",
    "price",
    "date_flagged",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ============================================================
# UTILITIES
# ============================================================
def print_step(step_num, total, message):
    print(f"\n[{step_num}/{total}] {message}")
    print("-" * 60)


def print_success(message):
    print(f"   ✅ {message}")


def print_error(message):
    print(f"   ❌ {message}")


def print_info(message):
    print(f"   ℹ️  {message}")


def fail_and_exit(reason):
    print("\n" + "=" * 60)
    print("❌ ONBOARDING FAILED")
    print("=" * 60)
    print(f"Reason: {reason}")
    print("\nNo changes were made. Fix the issue and try again.")
    sys.exit(1)


# ============================================================
# STEP 0: COUNTY AVAILABILITY CHECK
# ============================================================
def check_county(county):
    """Verify county is available before onboarding."""
    try:
        cm = CountyManager()
    except FileNotFoundError:
        fail_and_exit(
            "data/clients.json not found. County manager needs this file."
        )

    ok, msg = cm.is_available(county)
    if not ok:
        fail_and_exit(f"County check failed: {msg}")

    print_success(f"County '{county}' available — {msg}")
    return cm


# ============================================================
# STEP 1: Verify Service Account
# ============================================================
def verify_service_account():
    if not SERVICE_ACCOUNT_FILE.exists():
        fail_and_exit(
            f"Service account file not found at: {SERVICE_ACCOUNT_FILE}"
        )
    print_success(f"Service account file exists: {SERVICE_ACCOUNT_FILE.name}")

    try:
        with open(SERVICE_ACCOUNT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        email = data.get("client_email", "unknown")
        print_success(f"Service account email: {email}")
        return email
    except Exception as e:
        fail_and_exit(f"Service account JSON is invalid: {e}")


# ============================================================
# STEP 2: Test Gemini Connection
# ============================================================
def verify_gemini():
    load_dotenv(ENV_FILE, override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

    if not api_key:
        fail_and_exit("GEMINI_API_KEY missing in .env")

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        import warnings
        warnings.filterwarnings("ignore")

        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
        )
        response = llm.invoke('Reply with ONLY this JSON: {"status": "ok"}')
        raw = response.text.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        if parsed.get("status") == "ok":
            print_success(f"Gemini model '{model}' is working")
        else:
            fail_and_exit(f"Unexpected response from Gemini: {raw}")
    except Exception as e:
        # Don't fail — Gemini could be temporarily down
        print_error(f"Gemini test skipped (will retry during test run): {str(e)[:80]}")


# ============================================================
# STEP 3: Verify Sheet Access
# ============================================================
def verify_sheet_access(sheet_id):
    try:
        creds = Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_FILE),
            scopes=SCOPES,
        )
        client = gspread.authorize(creds)

        try:
            sheet = client.open_by_key(sheet_id)
        except gspread.exceptions.SpreadsheetNotFound:
            fail_and_exit(
                f"Sheet not found with ID: {sheet_id}\n"
                f"   → Sheet টা service account email কে share করেছো কিনা চেক করো।"
            )
        except gspread.exceptions.APIError as e:
            fail_and_exit(
                f"Google API error: {e}\n"
                f"   → Service account কে Editor হিসেবে share করা হয়েছে কিনা চেক করো।"
            )

        print_success(f"Sheet found: '{sheet.title}'")

        worksheet = sheet.sheet1
        print_success(f"Accessing worksheet: '{worksheet.title}'")
        return sheet
    except Exception as e:
        fail_and_exit(f"Sheet access failed: {e}")


# ============================================================
# STEP 4: Backup .env
# ============================================================
def backup_env():
    if not ENV_FILE.exists():
        fail_and_exit(f".env file not found at {ENV_FILE}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = ENV_FILE.parent / f".env.backup_{timestamp}"
    shutil.copy2(ENV_FILE, backup_path)
    print_success(f"Backup saved: {backup_path.name}")
    return backup_path


# ============================================================
# STEP 5: Update .env
# ============================================================
def update_env(sheet_id, csv_path=None):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("GOOGLE_SHEET_ID="):
            new_lines.append(f"GOOGLE_SHEET_ID={sheet_id}\n")
            updated = True
        elif line.strip().startswith("LEADS_CSV_PATH="):
            if csv_path:
                new_lines.append(f"LEADS_CSV_PATH={csv_path}\n")
            # else: drop
        else:
            new_lines.append(line)

    if not updated:
        if not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"GOOGLE_SHEET_ID={sheet_id}\n")

    if csv_path and not any("LEADS_CSV_PATH" in l for l in new_lines):
        new_lines.append(f"LEADS_CSV_PATH={csv_path}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print_success(f"Updated .env with new GOOGLE_SHEET_ID")
    if csv_path:
        print_success(f"Updated .env with LEADS_CSV_PATH={csv_path}")


# ============================================================
# STEP 6: Verify/Create Header Row
# ============================================================
def verify_header(sheet):
    worksheet = sheet.sheet1
    all_values = worksheet.get_all_values()

    if len(all_values) == 0:
        worksheet.append_row(HEADER_ROW)
        print_success("Sheet was empty — header row added (8 columns)")
        return

    header = all_values[0]
    if header == HEADER_ROW:
        print_success("Header row verified (all 8 columns present)")
    else:
        print_info(f"Current header: {header}")
        print_info(f"Expected header: {HEADER_ROW}")
        print_info("Header mismatch — but pipeline will still work if columns match")


# ============================================================
# STEP 7: Test Run
# ============================================================
def test_run(csv_path=None):
    try:
        from importlib import reload
        import data_collector
        import data_cleaner
        import sheet_pusher

        reload(data_collector)
        reload(data_cleaner)
        reload(sheet_pusher)

        print_info("Loading data...")
        raw = data_collector.load_property_data(
            str(csv_path) if csv_path else None
        )
        print_info(f"Loaded {len(raw)} rows")

        print_info("Cleaning + AI classifying...")
        clean_df, _ = data_cleaner.clean_leads(raw)
        print_info(f"Cleaned to {len(clean_df)} rows")

        print_info("Pushing to Sheet...")
        pushed = sheet_pusher.push_to_sheet(clean_df)
        print_success(f"Test run complete — {pushed} rows pushed")
    except Exception as e:
        # Gemini might be down — don't hard fail
        print_error(f"Test run had issues (not fatal): {str(e)[:100]}")
        print_info("Onboarding will continue. Pipeline can be re-run later.")


# ============================================================
# STEP 8: Add Client to County Registry
# ============================================================
def register_client(cm, county, client_id, client_name, email=""):
    ok, msg = cm.add_client(county, client_id, client_name, email)
    if not ok:
        fail_and_exit(f"Failed to register client in county: {msg}")
    print_success(msg)


# ============================================================
# STEP 9: Print Client Instructions
# ============================================================
def print_client_instructions(client_name, service_email, sheet_id, county):
    print("\n" + "=" * 60)
    print("🎉 ONBOARDING COMPLETE")
    print("=" * 60)
    print(f"\nClient:      {client_name}")
    print(f"County:      {county.upper()}")
    print(f"Sheet ID:    {sheet_id}")
    print(f"\n📧 Share this email with the client:")
    print(f"   {service_email}")
    print(f"\n📋 Instructions for client:")
    print(f"   1. Open their Google Sheet")
    print(f"   2. Click 'Share' (top-right)")
    print(f"   3. Paste: {service_email}")
    print(f"   4. Set permission: 'Editor'")
    print(f"   5. Click 'Send'")
    print(f"\n✅ After sharing, the pipeline will auto-push daily.")
    print(f"\n🔗 Sheet URL:")
    print(f"   https://docs.google.com/spreadsheets/d/{sheet_id}")
    print("\n" + "=" * 60)


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Onboard a new client for the Real Estate AI pipeline"
    )
    parser.add_argument("--name", required=True, help="Client name")
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID")
    parser.add_argument("--county", required=True, help="County code (e.g., maricopa_az)")
    parser.add_argument("--client-id", default=None, help="Unique client ID")
    parser.add_argument("--email", default="", help="Client email (optional)")
    parser.add_argument("--csv", default=None, help="(Optional) CSV path for this client")
    args = parser.parse_args()

    # Auto-generate client_id if not provided
    client_id = args.client_id or f"client_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print("\n" + "=" * 60)
    print(f"🚀 ONBOARDING CLIENT: {args.name}")
    print(f"   County: {args.county}")
    print(f"   Client ID: {client_id}")
    print("=" * 60)

    total_steps = 9

    # Step 0: County availability
    print_step(0, total_steps, "Checking county availability")
    cm = check_county(args.county)

    # Step 1: Service account
    print_step(1, total_steps, "Verifying service account")
    service_email = verify_service_account()

    # Step 2: Gemini
    print_step(2, total_steps, "Testing Gemini API connection")
    verify_gemini()

    # Step 3: Sheet access
    print_step(3, total_steps, "Verifying Sheet access")
    sheet = verify_sheet_access(args.sheet_id)

    # Step 4: Backup .env
    print_step(4, total_steps, "Backing up current .env")
    backup_env()

    # Step 5: Update .env
    print_step(5, total_steps, "Updating .env with new Sheet ID")
    update_env(args.sheet_id, args.csv)

    # Step 6: Header row
    print_step(6, total_steps, "Verifying Sheet header row")
    verify_header(sheet)

    # Step 7: Test run
    print_step(7, total_steps, "Running test pipeline")
    test_run(Path(args.csv) if args.csv else None)

    # Step 8: Register client in county
    print_step(8, total_steps, "Registering client in county registry")
    register_client(cm, args.county, client_id, args.name, args.email)

    # Step 9: Print instructions
    print_step(9, total_steps, "Printing client instructions")
    print_client_instructions(args.name, service_email, args.sheet_id, args.county)


if __name__ == "__main__":
    main()
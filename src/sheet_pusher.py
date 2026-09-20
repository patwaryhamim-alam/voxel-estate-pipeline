"""
Module 3: Sheet Pusher
Takes Module 2's clean DataFrame and appends rows to a Google Sheet.

DESIGN PRINCIPLE:
    push_to_sheet(df) is the ONLY public function.
    Input:  DataFrame with OUTPUT_COLUMNS from Module 2
    Output: (side-effect: writes to Google Sheet + logs)

INTEGRATED WITH:
    - RunSummary: tracks stats and sends summary email
    - Error alerts: sends email on failure
    - File Watcher: processes inbox/<client_id>/ CSVs

USAGE:
    python src/sheet_pusher.py                         # Process inbox
    python src/sheet_pusher.py --dry-run               # Preview only
    python src/sheet_pusher.py --client client_001     # Specific client
    python src/sheet_pusher.py --csv data/x.csv        # Direct CSV
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from logger import get_logger
from alerts import send_error_alert
from run_summary import RunSummary, send_summary_email
from file_watcher import (
    scan_inbox,
    move_to_processed,
    is_already_processed,
)

log = get_logger(__name__)

load_dotenv()

# ============================================================
# CONFIG
# ============================================================
SERVICE_ACCOUNT_FILE = "credentials/service_account.json"
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
DEFAULT_CLIENT = os.getenv("CLIENT_ID", "client_001")

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

PROJECT_ROOT = Path(__file__).parent.parent


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
    """
    Push clean DataFrame rows to Google Sheet (duplicate-safe).

    Returns:
        (pushed_count, skipped_count)
    """
    log.info(f"push_to_sheet() called with {len(df)} rows in DataFrame")

    missing = [c for c in OUTPUT_COLUMNS if c not in df.columns]
    if missing:
        log.error(f"Input DataFrame missing columns: {missing}")
        raise ValueError(f"Input DataFrame missing columns: {missing}")

    if len(df) == 0:
        print("[Sheet] 0 rows in input DataFrame.")
        log.info("Empty DataFrame — nothing to push.")
        return 0, 0

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
        return 0, len(df)

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

    return len(rows_to_add), skipped


# ============================================================
# PROCESS ONE CSV THROUGH FULL PIPELINE
# ============================================================
def process_one_csv(csv_path, summary, dry_run=False):
    """
    Process one CSV through Module 1 → 2 → 3.

    Args:
        csv_path: Path to CSV file
        summary: RunSummary object (stats accumulation)
        dry_run: If True, skip Sheet push and save preview CSV

    Returns:
        (success: bool, pushed: int, skipped: int)
    """
    from data_collector import load_property_data
    from data_cleaner import clean_leads

    print(f"\n{'='*60}")
    print(f"Processing: {csv_path.name}")
    print(f"{'='*60}")

    log.info(f"Loading: {csv_path}")
    raw = load_property_data(str(csv_path))

    # Accumulate input rows
    current_input = summary.input_rows
    summary.set_input_rows(current_input + len(raw))

    log.info(f"Cleaning and classifying...")
    clean_df, _ = clean_leads(raw, summary=summary)

    if dry_run:
        # Save preview only
        preview_path = PROJECT_ROOT / "output" / f"preview_{csv_path.stem}.csv"
        preview_path.parent.mkdir(exist_ok=True)
        clean_df.to_csv(preview_path, index=False)
        print(f"[DRY-RUN] Preview saved: {preview_path}")
        log.info(f"[DRY-RUN] Preview saved: {preview_path}")
        return True, 0, 0

    # Real push
    log.info(f"Pushing {len(clean_df)} rows to Sheet...")
    pushed, skipped = push_to_sheet(clean_df)

    return True, pushed, skipped


# ============================================================
# MAIN PIPELINE
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Voxel Estate Pipeline")
    parser.add_argument("--client", default=DEFAULT_CLIENT,
                        help=f"Client ID (default: {DEFAULT_CLIENT})")
    parser.add_argument("--csv", default=None,
                        help="Direct CSV path (skips inbox scan)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process without pushing to Sheet")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("PIPELINE RUN STARTED")
    log.info("=" * 60)

    if args.dry_run:
        print("🧪 DRY-RUN MODE — No Sheet push will happen\n")

    # Initialize summary
    summary = RunSummary(
        client_id=args.client,
        run_type="dry_run" if args.dry_run else "manual",
    )

    try:
        # Determine files to process
        if args.csv:
            # Direct CSV mode
            csv_path = Path(args.csv)
            if not csv_path.exists():
                raise FileNotFoundError(f"CSV not found: {csv_path}")
            files_to_process = [csv_path]
            print(f"[Mode] Direct CSV: {csv_path.name}")

        elif os.getenv("LEADS_CSV_PATH"):
            # Env override mode
            csv_path = Path(os.getenv("LEADS_CSV_PATH"))
            files_to_process = [csv_path]
            print(f"[Mode] Env override: {csv_path.name}")

        else:
            # Inbox scan mode (default)
            print(f"[Mode] Scanning inbox/{args.client}/...")
            files_to_process = scan_inbox(args.client)

            if not files_to_process:
                print(f"\n⚠️  No files in inbox/{args.client}/")
                print(f"   Place CSV at: inbox/{args.client}/leads.csv")
                print(f"   Or use --csv flag for direct path")
                log.info("No files to process")
                return

        # Process each file
        total_pushed = 0
        total_skipped = 0
        files_success = 0

        for csv_path in files_to_process:
            # Skip already-processed (content hash match)
            if not args.csv and not os.getenv("LEADS_CSV_PATH"):
                if is_already_processed(args.client, csv_path):
                    print(f"⏭️  Skipping (already processed): {csv_path.name}")
                    continue

            try:
                success, pushed, skipped = process_one_csv(
                    csv_path, summary, dry_run=args.dry_run
                )
                if success:
                    files_success += 1
                    total_pushed += pushed
                    total_skipped += skipped

                    # Move to processed (only if not dry-run)
                    if not args.dry_run:
                        move_to_processed(args.client, csv_path)
                    else:
                        print(f"[DRY-RUN] Would move to processed/: {csv_path.name}")

            except Exception as e:
                log.error(f"Failed to process {csv_path.name}: {e}")
                print(f"❌ Failed: {csv_path.name} — {e}")
                # Continue with next file

        # Finalize summary
        summary.set_sheet_stats(pushed=total_pushed, skipped=total_skipped)

        if files_success == len(files_to_process):
            summary.set_success()
        elif files_success > 0:
            summary.set_partial()
        else:
            summary.set_error("All files failed")

        summary.finish()

        print(f"\n{'='*60}")
        print(f"PIPELINE COMPLETE")
        print(f"{'='*60}")
        print(f"Files processed: {files_success}/{len(files_to_process)}")
        print(f"Rows pushed:     {total_pushed}")
        print(f"Duplicates:      {total_skipped}")

        log.info("PIPELINE RUN COMPLETED")

        # Print + send summary
        print("\n" + summary.to_text())
        ok, msg = send_summary_email(summary)
        if ok:
            print(f"\n📧 Summary email sent: {msg}")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        log.error(f"Pipeline failed: {e}", exc_info=True)

        summary.set_error(str(e)[:500])
        summary.finish()

        try:
            send_summary_email(summary)
        except Exception:
            pass

        success, msg = send_error_alert(
            subject="Pipeline Failed (sheet_pusher)",
            body=f"Error: {str(e)[:500]}",
            context=f"client: {args.client}",
            exc_info=sys.exc_info(),
        )
        if success:
            print(f"📧 Alert sent: {msg}")


if __name__ == "__main__":
    main()
"""
Module 3: Sheet Pusher
Takes Module 2's clean DataFrame and appends rows to a Google Sheet.

FIX 1: partial-run design (file stays inbox if pending)
FIX 5: reasoning delivered to Sheet (9th column, auto-header-extend)

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

# Fix 5: 9 columns — reason appended at END for backward-compat
OUTPUT_COLUMNS = [
    "owner_name",
    "address",
    "county",
    "owner_status",
    "phone",
    "signal_type",
    "price",
    "date_flagged",
    "reason",
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


def _ensure_header_has_all_columns(sheet, header):
    """
    Fix 5: Extend the sheet header if new columns (e.g. "reason")
    are missing. Existing rows are untouched — they simply have
    empty cells in the new column.

    Returns the (possibly updated) header list.
    """
    if not header:
        return header

    missing = [c for c in OUTPUT_COLUMNS if c not in header]
    if not missing:
        return header

    # Append missing columns to header row (positional extend)
    new_header = list(header) + missing
    try:
        sheet.update("A1", [new_header])
        log.info(f"Extended sheet header with: {missing}")
        print(f"[Sheet] Extended header with new columns: {missing}")
    except Exception as e:
        log.warning(f"Could not extend header: {e}")
        print(f"[Sheet] WARNING: could not extend header: {e}")

    return new_header


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================
def push_to_sheet(df):
    """
    Push clean DataFrame rows to Google Sheet (duplicate-safe).

    Fix 1: pending rows skipped.
    Fix 5: header auto-extended for new columns.

    Returns:
        (pushed_count, skipped_count, pending_count)
    """
    log.info(f"push_to_sheet() called with {len(df)} rows in DataFrame")

    missing = [c for c in OUTPUT_COLUMNS if c not in df.columns]
    if missing:
        log.error(f"Input DataFrame missing columns: {missing}")
        raise ValueError(f"Input DataFrame missing columns: {missing}")

    if len(df) == 0:
        print("[Sheet] 0 rows in input DataFrame.")
        log.info("Empty DataFrame — nothing to push.")
        return 0, 0, 0

    # Filter out pending rows
    df = df.copy()
    pending_count = 0
    if "signal_type" in df.columns:
        pending_count = int((df["signal_type"] == "pending").sum())
        if pending_count > 0:
            print(f"[Sheet] Skipping {pending_count} pending leads "
                  f"(will retry next run)")
            log.warning(f"Skipping {pending_count} pending leads")
            df = df[df["signal_type"] != "pending"].copy()

    if len(df) == 0:
        print("[Sheet] All rows pending — nothing to push this run.")
        return 0, 0, pending_count

    print(f"[Sheet] Connecting to Google Sheets...")
    log.info("Connecting to Google Sheets...")
    client = _get_client()
    sheet = client.open_by_key(SHEET_ID).sheet1

    existing = sheet.get_all_values()
    if len(existing) == 0:
        # Fresh sheet — write full header
        sheet.append_row(OUTPUT_COLUMNS)
        header = OUTPUT_COLUMNS
        existing_data = []
        log.info("Sheet was empty — wrote header row.")
    else:
        header = existing[0]
        # Fix 5: auto-extend header if new columns missing
        header = _ensure_header_has_all_columns(sheet, header)
        existing_data = existing[1:]

    # Owner/address column index lookup (uses current header)
    try:
        owner_idx = header.index("owner_name")
        address_idx = header.index("address")
    except ValueError:
        log.error("Sheet header missing 'owner_name' or 'address' column.")
        raise ValueError(
            "Sheet header must contain 'owner_name' and 'address' columns."
        )

    # Build existing keys for duplicate detection
    existing_keys = set()
    for row in existing_data:
        if len(row) > max(owner_idx, address_idx):
            key = f"{row[owner_idx].strip().lower()}||{row[address_idx].strip().lower()}"
            existing_keys.add(key)

    print(f"[Sheet] Found {len(existing_keys)} existing leads in sheet.")
    log.info(f"Found {len(existing_keys)} existing leads in sheet.")

    df["_key"] = df.apply(_make_lead_key, axis=1)
    new_rows_df = df[~df["_key"].isin(existing_keys)].drop(columns=["_key"])

    if len(new_rows_df) == 0:
        msg = f"No new rows to push — all {len(df)} leads already in sheet."
        print(f"[Sheet] SKIP: {msg}")
        log.info(msg)
        return 0, len(df), pending_count

    rows_to_add = new_rows_df[OUTPUT_COLUMNS].values.tolist()
    sheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")

    rows_after = len(existing_data) + len(rows_to_add)
    skipped = len(df) - len(rows_to_add)

    print(f"[Sheet] Pushed {len(rows_to_add)} new rows.")
    print(f"[Sheet]    Skipped {skipped} duplicates.")
    print(f"[Sheet]    Total rows now: {rows_after}")
    print(f"[Sheet]    Sheet URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}")

    log.info(
        f"Pushed {len(rows_to_add)} new rows, skipped {skipped} duplicates, "
        f"total rows now: {rows_after}"
    )

    return len(rows_to_add), skipped, pending_count


# ============================================================
# PROCESS ONE CSV
# ============================================================
def process_one_csv(csv_path, summary, dry_run=False):
    """Process one CSV through Module 1 → 2 → 3."""
    from data_collector import load_property_data
    from data_cleaner import clean_leads

    print(f"\n{'='*60}")
    print(f"Processing: {csv_path.name}")
    print(f"{'='*60}")

    log.info(f"Loading: {csv_path}")
    raw = load_property_data(str(csv_path))

    current_input = summary.input_rows
    summary.set_input_rows(current_input + len(raw))

    log.info(f"Cleaning and classifying...")
    clean_df, detail_df = clean_leads(raw, summary=summary)

    pending_count = detail_df.attrs.get("partial_count", 0)

    if dry_run:
        preview_path = PROJECT_ROOT / "output" / f"preview_{csv_path.stem}.csv"
        preview_path.parent.mkdir(exist_ok=True)
        clean_df.to_csv(preview_path, index=False)
        print(f"[DRY-RUN] Preview saved: {preview_path}")
        log.info(f"[DRY-RUN] Preview saved: {preview_path}")
        fully_done = (pending_count == 0)
        return fully_done, 0, 0, pending_count

    log.info(f"Pushing {len(clean_df)} rows to Sheet...")
    pushed, skipped, sheet_pending = push_to_sheet(clean_df)

    fully_done = (pending_count == 0) and (sheet_pending == 0)
    return fully_done, pushed, skipped, pending_count


# ============================================================
# MAIN PIPELINE
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Voxel Estate Pipeline")
    parser.add_argument("--client", default=DEFAULT_CLIENT)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("PIPELINE RUN STARTED")
    log.info("=" * 60)

    if args.dry_run:
        print("DRY-RUN MODE — No Sheet push will happen\n")

    summary = RunSummary(
        client_id=args.client,
        run_type="dry_run" if args.dry_run else "manual",
    )

    try:
        if args.csv:
            csv_path = Path(args.csv)
            if not csv_path.exists():
                raise FileNotFoundError(f"CSV not found: {csv_path}")
            files_to_process = [csv_path]
            print(f"[Mode] Direct CSV: {csv_path.name}")
        elif os.getenv("LEADS_CSV_PATH"):
            csv_path = Path(os.getenv("LEADS_CSV_PATH"))
            files_to_process = [csv_path]
            print(f"[Mode] Env override: {csv_path.name}")
        else:
            print(f"[Mode] Scanning inbox/{args.client}/...")
            files_to_process = scan_inbox(args.client)
            if not files_to_process:
                print(f"\nWARNING: No files in inbox/{args.client}/")
                print(f"   Place CSV at: inbox/{args.client}/leads.csv")
                print(f"   Or use --csv flag for direct path")
                log.info("No files to process")
                return

        total_pushed = 0
        total_skipped = 0
        total_pending = 0
        files_fully_done = 0
        files_partial = 0
        files_failed = 0

        for csv_path in files_to_process:
            if not args.csv and not os.getenv("LEADS_CSV_PATH"):
                if is_already_processed(args.client, csv_path):
                    print(f"SKIP (already processed): {csv_path.name}")
                    continue

            try:
                fully_done, pushed, skipped, pending_count = process_one_csv(
                    csv_path, summary, dry_run=args.dry_run
                )
                total_pushed += pushed
                total_skipped += skipped
                total_pending += pending_count

                if fully_done:
                    files_fully_done += 1
                    if not args.dry_run:
                        move_to_processed(args.client, csv_path)
                    else:
                        print(f"[DRY-RUN] Would move to processed/: {csv_path.name}")
                else:
                    files_partial += 1
                    print(f"[Partial] {csv_path.name} STAYS in inbox "
                          f"({pending_count} leads pending — retry next run)")
                    log.warning(f"{csv_path.name} partially processed — "
                                f"staying in inbox for retry")

            except Exception as e:
                log.error(f"Failed to process {csv_path.name}: {e}")
                print(f"FAILED: {csv_path.name} — {e}")
                files_failed += 1

        summary.set_sheet_stats(pushed=total_pushed, skipped=total_skipped)

        if hasattr(summary, "set_partial_info"):
            summary.set_partial_info(
                files_partial=files_partial,
                files_done=files_fully_done,
                leads_pending=total_pending,
            )

        if files_failed == 0 and files_partial == 0:
            summary.set_success()
        elif files_fully_done > 0 or files_partial > 0:
            summary.set_partial()
        else:
            summary.set_error("All files failed")

        summary.finish()

        print(f"\n{'='*60}")
        print(f"PIPELINE COMPLETE")
        print(f"{'='*60}")
        print(f"Files fully processed: {files_fully_done}/{len(files_to_process)}")
        print(f"Files partial:         {files_partial}")
        print(f"Files failed:          {files_failed}")
        print(f"Rows pushed:           {total_pushed}")
        print(f"Duplicates:            {total_skipped}")
        print(f"Leads pending:         {total_pending}")

        log.info("PIPELINE RUN COMPLETED")

        print("\n" + summary.to_text())
        ok, msg = send_summary_email(summary)
        if ok:
            print(f"\n[EMAIL] Summary sent: {msg}")

    except Exception as e:
        print(f"\nERROR: {e}")
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
            print(f"[EMAIL] Alert sent: {msg}")


if __name__ == "__main__":
    main()
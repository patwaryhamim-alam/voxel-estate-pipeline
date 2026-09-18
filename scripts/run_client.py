"""
SINGLE CLIENT PIPELINE RUNNER
=============================
Runs the full pipeline for ONE client based on their config file.

USAGE:
    python scripts/run_client.py --client-id client_001
    python scripts/run_client.py --client-id client_001 --dry-run
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
from alerts import send_error_alert


CONFIG_DIR = PROJECT_ROOT / "configs" / "clients"


def print_header(message):
    print("\n" + "=" * 70)
    print(f"  {message}")
    print("=" * 70)


def fail(reason, context="", exc_info=None):
    """Print failure and optionally send email alert."""
    print(f"\n❌ FAILED: {reason}")

    # Send alert if context provided
    if context:
        success, msg = send_error_alert(
            subject=f"Pipeline Failed: {context}",
            body=f"Error: {reason}",
            context=context,
            exc_info=exc_info,
        )
        if success:
            print(f"📧 Alert sent: {msg}")

    sys.exit(1)


def load_client_config(client_id):
    config_file = CONFIG_DIR / f"{client_id}.json"
    if not config_file.exists():
        fail(
            f"Client config not found: {config_file}",
            context=f"client:{client_id}",
        )

    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    required = ["client_id", "name", "county", "sheet_id", "csv_path"]
    missing = [k for k in required if k not in config]
    if missing:
        fail(
            f"Client config missing required fields: {missing}",
            context=f"client:{client_id}",
        )

    return config


def verify_csv(csv_path, context=""):
    csv_full = PROJECT_ROOT / csv_path
    if not csv_full.exists():
        fail(
            f"CSV file not found: {csv_full}",
            context=context,
        )
    return csv_full


def main():
    parser = argparse.ArgumentParser(description="Run pipeline for ONE client")
    parser.add_argument("--client-id", required=True, help="Client ID (e.g., client_001)")
    parser.add_argument("--dry-run", action="store_true", help="Verify config without running pipeline")
    args = parser.parse_args()

    client_id = args.client_id

    print_header(f"🚀 RUNNING PIPELINE FOR: {client_id}")

    print(f"\n[1/4] Loading config: configs/clients/{client_id}.json")
    config = load_client_config(client_id)
    print(f"   ✅ Client: {config['name']}")
    print(f"   ✅ County: {config['county']}")
    print(f"   ✅ Sheet ID: {config['sheet_id'][:20]}...")

    print(f"\n[2/4] Checking client status")
    if not config.get("active", True):
        print(f"   ⏸️  Client is INACTIVE — skipping")
        sys.exit(0)
    print(f"   ✅ Client is active")

    print(f"\n[3/4] Verifying CSV file")
    csv_full = verify_csv(config["csv_path"], context=f"client:{client_id}")
    print(f"   ✅ CSV found: {csv_full.name}")

    print(f"\n[4/4] Running pipeline")

    os.environ["GOOGLE_SHEET_ID"] = config["sheet_id"]
    os.environ["LEADS_CSV_PATH"] = str(csv_full)

    if args.dry_run:
        print("\n" + "=" * 70)
        print("  🧪 DRY RUN — Config verified, pipeline not executed")
        print("=" * 70)
        print(f"  Would run pipeline for: {config['name']}")
        print(f"  CSV:   {csv_full}")
        print(f"  Sheet: {config['sheet_id']}")
        print("=" * 70)
        sys.exit(0)

    from importlib import reload
    import data_collector
    import data_cleaner
    import sheet_pusher

    reload(data_collector)
    reload(data_cleaner)
    reload(sheet_pusher)

    try:
        print("\n" + "-" * 70)
        print(f"  PIPELINE EXECUTION")
        print("-" * 70)

        raw = data_collector.load_property_data(str(csv_full))
        clean_df, _ = data_cleaner.clean_leads(raw)
        pushed = sheet_pusher.push_to_sheet(clean_df)

        print("\n" + "=" * 70)
        print(f"  ✅ PIPELINE COMPLETE FOR: {config['name']}")
        print(f"     Rows pushed: {pushed}")
        print(f"     Timestamp:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

    except Exception as e:
        print("\n" + "=" * 70)
        print(f"  ❌ PIPELINE FAILED FOR: {config['name']}")
        print(f"     Error: {str(e)[:200]}")
        print("=" * 70)

        # Send email alert with full traceback
        success, msg = send_error_alert(
            subject=f"Pipeline Failed: {config['name']}",
            body=(
                f"Client: {config['name']} ({config['client_id']})\n"
                f"County: {config['county']}\n"
                f"CSV: {config['csv_path']}\n"
                f"Error: {str(e)[:500]}"
            ),
            context=f"{config['client_id']}",
            exc_info=sys.exc_info(),
        )
        if success:
            print(f"   📧 Alert sent: {msg}")
        else:
            print(f"   ⚠️  Alert failed: {msg}")

        sys.exit(1)


if __name__ == "__main__":
    main()
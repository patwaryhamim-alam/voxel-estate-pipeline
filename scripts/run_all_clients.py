"""
RUN ALL CLIENTS PIPELINE
========================
Runs the pipeline for EVERY active client in configs/clients/.

USAGE:
    python scripts/run_all_clients.py
    python scripts/run_all_clients.py --dry-run

WHAT IT DOES:
    1. Loads all client configs from configs/clients/*.json
    2. Filters to active clients only
    3. Runs each client's pipeline sequentially
    4. Prints a summary report (success/failure per client)
    5. Failures do NOT stop other clients — isolated

If one client fails, others continue.
"""

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Add src/ to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================
CONFIG_DIR = PROJECT_ROOT / "configs" / "clients"


# ============================================================
# HELPERS
# ============================================================
def print_header(message):
    print("\n" + "=" * 70)
    print(f"  {message}")
    print("=" * 70)


def load_all_configs():
    """Load all client JSON configs from configs/clients/."""
    if not CONFIG_DIR.exists():
        print(f"❌ Config directory not found: {CONFIG_DIR}")
        sys.exit(1)

    configs = []
    for config_file in sorted(CONFIG_DIR.glob("*.json")):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["_config_file"] = config_file.name
            configs.append(cfg)
        except Exception as e:
            print(f"⚠️  Skipped {config_file.name}: {e}")

    return configs


def run_one_client(config, dry_run=False):
    """
    Run pipeline for a single client.
    Returns (success: bool, message: str, rows_pushed: int)
    """
    client_id = config.get("client_id", "unknown")
    name = config.get("name", "Unknown")

    try:
        # Verify required fields
        required = ["client_id", "name", "county", "sheet_id", "csv_path"]
        missing = [k for k in required if k not in config]
        if missing:
            return False, f"Missing fields: {missing}", 0

        # Check active
        if not config.get("active", True):
            return None, "INACTIVE — skipped", 0

        # Verify CSV exists
        csv_path = PROJECT_ROOT / config["csv_path"]
        if not csv_path.exists():
            return False, f"CSV not found: {config['csv_path']}", 0

        if dry_run:
            return True, f"DRY-RUN OK (CSV: {csv_path.name})", 0

        # Import and reload for fresh env per client
        from importlib import reload
        import os
        import data_collector
        import data_cleaner
        import sheet_pusher

        # Set env vars for this client
        os.environ["GOOGLE_SHEET_ID"] = config["sheet_id"]

        # Reload modules to pick up new env
        reload(data_collector)
        reload(data_cleaner)
        reload(sheet_pusher)

        # Run pipeline with explicit CSV path
        raw = data_collector.load_property_data(str(csv_path))
        clean_df, _ = data_cleaner.clean_leads(raw)
        pushed = sheet_pusher.push_to_sheet(clean_df)

        return True, f"{pushed} rows pushed", pushed

    except Exception as e:
        return False, f"Error: {str(e)[:120]}", 0


def main():
    parser = argparse.ArgumentParser(description="Run pipeline for ALL clients")
    parser.add_argument("--dry-run", action="store_true", help="Verify configs without running")
    args = parser.parse_args()

    start_time = datetime.now()

    print_header(f"🚀 RUNNING ALL CLIENTS  |  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Load configs
    configs = load_all_configs()
    print(f"\nFound {len(configs)} client config(s)")

    if len(configs) == 0:
        print("⚠️  No client configs found in configs/clients/")
        sys.exit(1)

    # Filter to active
    active_configs = [c for c in configs if c.get("active", True)]
    inactive_count = len(configs) - len(active_configs)
    print(f"Active: {len(active_configs)}  |  Inactive: {inactive_count}")

    # Results tracking
    results = []

    # Run each client
    for i, config in enumerate(active_configs, 1):
        client_id = config.get("client_id", "unknown")
        name = config.get("name", "Unknown")

        print("\n" + "-" * 70)
        print(f"[{i}/{len(active_configs)}] {client_id} — {name}")
        print("-" * 70)

        success, message, rows = run_one_client(config, dry_run=args.dry_run)
        results.append({
            "client_id": client_id,
            "name": name,
            "success": success,
            "message": message,
            "rows": rows,
        })

        if success is True:
            print(f"   ✅ {message}")
        elif success is False:
            print(f"   ❌ {message}")
        else:
            print(f"   ⏸️  {message}")

    # Summary report
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print_header("📊 SUMMARY REPORT")

    success_count = sum(1 for r in results if r["success"] is True)
    fail_count = sum(1 for r in results if r["success"] is False)
    skip_count = sum(1 for r in results if r["success"] is None)
    total_rows = sum(r["rows"] for r in results)

    print(f"\nTotal clients:   {len(results)}")
    print(f"✅ Success:      {success_count}")
    print(f"❌ Failed:       {fail_count}")
    print(f"⏸️  Skipped:      {skip_count}")
    print(f"📤 Total rows:   {total_rows}")
    print(f"⏱️  Duration:     {duration:.1f}s")

    print("\n" + "-" * 70)
    print("Per-client results:")
    print("-" * 70)
    for r in results:
        icon = "✅" if r["success"] is True else ("❌" if r["success"] is False else "⏸️")
        print(f"  {icon} {r['client_id']:15} | {r['name']:20} | {r['message']}")

    print("\n" + "=" * 70)

    # Exit code: 0 if all succeeded, 1 if any failed
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
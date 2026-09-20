"""
Module 1: Data Collector
Reads property leads data and returns a standardized DataFrame.

SUPPORTED INPUT FORMATS:
    - Standard CSV (with owner_mailing_address)
    - PropStream CSV
    - Excel files (.xlsx, .xls)
"""

import pandas as pd


# ============================================================
# THE CONTRACT — includes owner_mailing_address
# ============================================================
EXPECTED_COLUMNS = [
    "owner_name",
    "address",
    "owner_mailing_address",
    "phone",
    "listing_type",
    "list_price",
    "previous_price",
    "county",
    "distress_signals",  # NEW
]

DEFAULT_DATA_FILE = "data/property_leads.csv"
CSV_FILE = DEFAULT_DATA_FILE


# ============================================================
# FORMAT DETECTION
# ============================================================
def _detect_format(df):
    """Detect the format of the DataFrame."""
    cols = set(df.columns)

    # Standard format: check required columns (distress_signals optional)
    required_standard = [c for c in EXPECTED_COLUMNS if c != "distress_signals"]
    if set(required_standard).issubset(cols):
        return "standard"
        
    propstream_markers = {
        "Owner First Name", "Owner Last Name", "Property Address",
        "For Sale By Owner", "Listing Price",
    }
    if propstream_markers.issubset(cols):
        return "propstream"

    return "unknown"


# ============================================================
# MAIN FUNCTION
# ============================================================
def load_property_data(file_path=None):
    """Load property leads. Supports .csv, .xlsx, .xls."""
    path = file_path or CSV_FILE

    path_str = str(path).lower()
    if path_str.endswith(".csv"):
        df = pd.read_csv(path)
    elif path_str.endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    else:
        raise ValueError(
            f"Unsupported file type: {path}. Use .csv, .xlsx, or .xls"
        )

    fmt = _detect_format(df)
    print(f"[Module 1] Detected format: {fmt}")

    if fmt == "standard":
        # Check required columns (distress_signals is optional)
        required_cols = [c for c in EXPECTED_COLUMNS if c != "distress_signals"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"CSV is missing required columns: {missing}")
        # Add distress_signals if missing
        if "distress_signals" not in df.columns:
            df["distress_signals"] = ""
        df = df[EXPECTED_COLUMNS]

    elif fmt == "propstream":
        from adapter import adapt_propstream
        df = adapt_propstream(df)

    else:
        raise ValueError(
            f"Unsupported CSV format. Columns found: {df.columns.tolist()}"
        )

    return df


# ============================================================
# PRESENTATION
# ============================================================
def print_summary(df):
    """Pretty-print a summary of the loaded data."""
    total = len(df)
    fsbo = len(df[df["listing_type"] == "FSBO"])
    price_drop = len(df[df["listing_type"] == "price_drop"])
    missing_owner = df["owner_name"].isna().sum()
    missing_address = df["address"].isna().sum()

    print("=" * 55)
    print("       PROPERTY LEADS — DATA SUMMARY")
    print("=" * 55)
    print(f"  Total leads          : {total}")
    print(f"  FSBO                 : {fsbo}")
    print(f"  Price Drop           : {price_drop}")
    print("-" * 55)
    print(f"  Missing owner_name   : {missing_owner}")
    print(f"  Missing address      : {missing_address}")
    print("=" * 55)

    print("\nColumns detected:")
    for col in df.columns:
        print(f"  • {col}")

    print("\nPreview (first 3 rows):")
    print(df.head(3).to_string(index=False))


def main():
    try:
        df = load_property_data()
        print_summary(df)
    except FileNotFoundError:
        print(f"ERROR: '{CSV_FILE}' pawa jay ni. data/ folder check koro.")
    except ValueError as e:
        print(f"ERROR: {e}")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
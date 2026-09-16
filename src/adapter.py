"""
ADAPTER LAYER
Converts external CSV formats into our standard format.
"""

import pandas as pd


EXPECTED_COLUMNS = [
    "owner_name",
    "address",
    "owner_mailing_address",
    "phone",
    "listing_type",
    "list_price",
    "previous_price",
    "county",
]


# ============================================================
# HELPERS
# ============================================================
def _combine_name(first, last):
    parts = []
    for val in [first, last]:
        if pd.notna(val) and str(val).strip():
            parts.append(str(val).strip())
    return " ".join(parts) if parts else None


def _combine_address(street, city, state):
    parts = []
    for val in [street, city, state]:
        if pd.notna(val) and str(val).strip():
            parts.append(str(val).strip())
    return " ".join(parts) if parts else None


def _determine_listing_type(fsbo, price_drop):
    fsbo_yes = pd.notna(fsbo) and str(fsbo).strip().lower() == "yes"
    drop_yes = pd.notna(price_drop) and str(price_drop).strip().lower() == "yes"
    if fsbo_yes:
        return "FSBO"
    if drop_yes:
        return "price_drop"
    return "price_drop"


def _safe_number(val, default=None):
    if pd.isna(val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ============================================================
# PROPSTREAM ADAPTER
# ============================================================
def adapt_propstream(raw_df):
    """Convert a PropStream CSV to our standard format."""
    required_input_cols = [
        "Owner First Name", "Owner Last Name", "Property Address",
        "City", "State", "County Name", "Listing Price", "Original Price",
        "For Sale By Owner", "Price Drop Flag",
    ]
    missing = [c for c in required_input_cols if c not in raw_df.columns]
    if missing:
        raise ValueError(f"PropStream CSV missing columns: {missing}")

    adapted = pd.DataFrame()

    adapted["owner_name"] = raw_df.apply(
        lambda row: _combine_name(row["Owner First Name"], row["Owner Last Name"]),
        axis=1,
    )
    adapted["address"] = raw_df.apply(
        lambda row: _combine_address(
            row["Property Address"], row["City"], row["State"]
        ),
        axis=1,
    )

    # Owner mailing address (optional columns)
    if "Mail Address" in raw_df.columns:
        adapted["owner_mailing_address"] = raw_df.apply(
            lambda row: _combine_address(
                row.get("Mail Address"),
                row.get("Mail City"),
                row.get("Mail State"),
            ),
            axis=1,
        )
    else:
        adapted["owner_mailing_address"] = None

    # Owner phone (optional)
    if "Phone" in raw_df.columns:
        adapted["phone"] = raw_df["Phone"]
    elif "Owner Phone" in raw_df.columns:
        adapted["phone"] = raw_df["Owner Phone"]
    else:
        adapted["phone"] = None


    adapted["listing_type"] = raw_df.apply(
        lambda row: _determine_listing_type(
            row["For Sale By Owner"], row["Price Drop Flag"]
        ),
        axis=1,
    )
    adapted["list_price"] = raw_df["Listing Price"].apply(_safe_number)
    adapted["previous_price"] = raw_df["Original Price"].apply(_safe_number)
    adapted["county"] = raw_df["County Name"]

    adapted = adapted[EXPECTED_COLUMNS]
    return adapted


def load_from_propstream(file_path):
    raw_df = pd.read_csv(file_path)
    return adapt_propstream(raw_df)
"""
ADAPTER LAYER (v2 — Flexible Column Mapping)
============================================
Converts external CSV formats into our standard format.

KEY FEATURES:
    - Case-insensitive column matching
    - Alias-based mapping (multiple names → one field)
    - Supports: PropStream, BatchLeads, Zillow, custom
    - Auto-format detection via column signatures
    - Clear error messages for unknown formats

DESIGN:
    Each source has its own adapter function.
    Downstream modules (2, 3) never know which source was used.
"""

import pandas as pd
from typing import Optional, Dict, List


# ============================================================
# OUTPUT CONTRACT — Module 2 expects these columns
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

DISTRESS_ALIASES = {
    "tax_delinquent": [
        "tax delinquent", "tax_delinquent", "delinquent",
        "tax lien", "tax default", "back taxes",
    ],
    "vacant": [
        "vacant", "vacancy", "vacant property", "is_vacant",
        "abandoned", "unoccupied",
    ],
    "pre_foreclosure": [
        "pre-foreclosure", "pre_foreclosure", "preforeclosure",
        "pre foreclosure", "in foreclosure", "notice of default",
        "nod", "lis pendens",
    ],
    "expired_listing": [
        "expired listing", "expired_listing", "expired",
        "listing expired",
    ],
    "divorce": [
        "divorce", "divorced", "divorce filing",
    ],
    "probate": [
        "probate", "estate", "inherited", "deceased",
    ],
}



# ============================================================
# COLUMN ALIASES — map many possible names to one canonical name
# ============================================================
COLUMN_ALIASES = {
    # --- First Name ---
    
    "first_name": [
        "owner first name", "first name", "firstname", "first",
        "owner 1 first name", "owner_first_name", "ownerfirstname",
        "fname", "given name",
    ],
    # --- Last Name ---
    "last_name": [
        "owner last name", "last name", "lastname", "last",
        "owner 1 last name", "owner_last_name", "ownerlastname",
        "surname", "family name", "lname",
    ],
    # --- Full Name (if not split) ---
    "full_name": [
        "owner name", "owner full name", "owner 1 full name",
        "ownername", "name", "contact name", "owner_name",
        "taxpayer name", "mailing name",
    ],
    # --- Street Address ---
    "street": [
        "property address", "address", "street address", "site address",
        "property street", "street", "property_address", "situs address",
        "site_address", "mail address", "mailing address",
    ],
    # --- City ---
    "city": [
        "city", "property city", "site city", "situs city",
        "mail city", "mailing city",
    ],
    # --- State ---
    "state": [
        "state", "property state", "site state", "situs state",
        "mail state", "mailing state", "st",
    ],
    # --- County ---
    "county": [
        "county", "county name", "property county", "county_name",
        "site county", "situs county",
    ],
    # --- Listing Price ---
    "list_price": [
        "listing price", "list price", "price", "asking price",
        "current price", "listing_price", "list_price",
    ],
    # --- Previous Price ---
    "previous_price": [
        "original price", "previous price", "original_price",
        "previous_price", "last price", "prior price",
    ],
    # --- FSBO Flag ---
    "fsbo": [
        "for sale by owner", "fsbo", "for_sale_by_owner",
        "is fsbo", "by owner",
    ],
    # --- Price Drop Flag ---
    "price_drop": [
        "price drop flag", "price drop", "price_drop", "price_drop_flag",
        "recent price drop", "price reduced",
    ],
    # --- Phone ---
    "phone": [
        "phone", "owner phone", "phone number", "phone_number",
        "telephone", "contact phone", "mobile",
    ],
}


def _normalize(s: str) -> str:
    """Lowercase, strip, remove extra spaces and underscores."""
    if s is None:
        return ""
    return str(s).strip().lower().replace("_", " ").replace("-", " ")


def _build_lookup(df_columns: List[str]) -> Dict[str, str]:
    """
    Build a lookup: normalized_column → original_column.
    Handles case-insensitivity and whitespace variations.
    """
    lookup = {}
    for col in df_columns:
        normalized = _normalize(col)
        lookup[normalized] = col
    return lookup


def _find_column(df_columns: List[str], alias_key: str) -> Optional[str]:
    """
    Find the original column name that matches any alias for `alias_key`.

    Returns:
        Original column name (str) or None if not found
    """
    aliases = COLUMN_ALIASES.get(alias_key, [])
    lookup = _build_lookup(df_columns)

    for alias in aliases:
        normalized_alias = _normalize(alias)
        if normalized_alias in lookup:
            return lookup[normalized_alias]

    return None


# ============================================================
# HELPERS — combine fields
# ============================================================
def _safe_str(val) -> str:
    """Convert value to clean string or empty."""
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip()


def _combine_name(first, last, full):
    """Build owner_name from available fields."""
    # Try first + last
    f = _safe_str(first)
    l = _safe_str(last)
    if f or l:
        return f"{f} {l}".strip()

    # Fallback to full name field
    return _safe_str(full)


def _combine_address(street, city, state):
    """Build full address from street + city + state."""
    parts = [_safe_str(street), _safe_str(city), _safe_str(state)]
    parts = [p for p in parts if p]
    return " ".join(parts) if parts else None


def _determine_listing_type(fsbo, price_drop):
    """Determine listing_type from flags."""
    fsbo_yes = _safe_str(fsbo).lower() in ("yes", "y", "true", "1")
    drop_yes = _safe_str(price_drop).lower() in ("yes", "y", "true", "1")

    if fsbo_yes:
        return "FSBO"
    if drop_yes:
        return "price_drop"
    return "price_drop"  # default


def _safe_number(val, default=None):
    """Convert to float safely."""
    if pd.isna(val) or val is None or val == "":
        return default
    try:
        # Strip $ and commas
        s = str(val).replace("$", "").replace(",", "").strip()
        return float(s)
    except (ValueError, TypeError):
        return default


# ============================================================
# UNIVERSAL ADAPTER — works with any column layout
# ============================================================
def adapt_generic(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Universal adapter — uses column aliases to find fields.
    Works with PropStream, BatchLeads, Zillow, and custom CSVs.
    """
    cols = raw_df.columns.tolist()

    # Find columns via aliases
    first_col = _find_column(cols, "first_name")
    last_col = _find_column(cols, "last_name")
    full_col = _find_column(cols, "full_name")
    street_col = _find_column(cols, "street")
    city_col = _find_column(cols, "city")
    state_col = _find_column(cols, "state")
    county_col = _find_column(cols, "county")
    list_price_col = _find_column(cols, "list_price")
    prev_price_col = _find_column(cols, "previous_price")
    fsbo_col = _find_column(cols, "fsbo")
    drop_col = _find_column(cols, "price_drop")
    phone_col = _find_column(cols, "phone")

    # Validate: need at least address
    if not street_col:
        raise ValueError(
            f"Could not find address column. Looked for: "
            f"{COLUMN_ALIASES['street'][:3]}...\n"
            f"Available columns: {cols}"
        )

    # Build output
    adapted = pd.DataFrame()

    # Owner name
    if first_col or last_col or full_col:
        adapted["owner_name"] = raw_df.apply(
            lambda r: _combine_name(
                r.get(first_col) if first_col else None,
                r.get(last_col) if last_col else None,
                r.get(full_col) if full_col else None,
            ),
            axis=1,
        )
    else:
        adapted["owner_name"] = None

    # Address
    adapted["address"] = raw_df.apply(
        lambda r: _combine_address(
            r.get(street_col) if street_col else None,
            r.get(city_col) if city_col else None,
            r.get(state_col) if state_col else None,
        ),
        axis=1,
    )

    # Mailing address (optional — same fields, may not exist)
    mail_col = _find_column(cols, "street")  # for now, same as property
    adapted["owner_mailing_address"] = None

    # Phone
    adapted["phone"] = raw_df[phone_col] if phone_col else None

    # Listing type
    if fsbo_col or drop_col:
        adapted["listing_type"] = raw_df.apply(
            lambda r: _determine_listing_type(
                r.get(fsbo_col) if fsbo_col else None,
                r.get(drop_col) if drop_col else None,
            ),
            axis=1,
        )
    else:
        adapted["listing_type"] = "price_drop"

    # Prices
    adapted["list_price"] = (
        raw_df[list_price_col].apply(_safe_number) if list_price_col else None
    )
    adapted["previous_price"] = (
        raw_df[prev_price_col].apply(_safe_number) if prev_price_col else None
    )

    # County
    adapted["county"] = raw_df[county_col] if county_col else None

      # ============================================================
    # Distress signals (NEW — extract optional columns)
    # ============================================================
    distress_signals = []
    for signal_name, aliases in DISTRESS_ALIASES.items():
        # Find matching column
        col = None
        for alias in aliases:
            normalized_alias = _normalize(alias)
            for original_col in cols:
                if _normalize(original_col) == normalized_alias:
                    col = original_col
                    break
            if col:
                break

        if col:
            # Check if any row has a truthy value
            values = raw_df[col].astype(str).str.strip().str.lower()
            has_signal = values.isin(["yes", "y", "true", "1"]).any()
            if has_signal:
                distress_signals.append(signal_name)

    # Add as comma-separated string column
    adapted["distress_signals"] = ",".join(distress_signals) if distress_signals else ""

    # Force column order (add distress at the end)
    adapted = adapted[EXPECTED_COLUMNS + ["distress_signals"]]
    return adapted

# ============================================================
# BACKWARD-COMPAT: adapt_propstream() still works
# ============================================================
def adapt_propstream(raw_df: pd.DataFrame) -> pd.DataFrame:
    """PropStream adapter — now uses universal adapter internally."""
    return adapt_generic(raw_df)


def load_from_propstream(file_path: str) -> pd.DataFrame:
    raw_df = pd.read_csv(file_path)
    return adapt_propstream(raw_df)


# ============================================================
# FORMAT DETECTION (used by data_collector)
# ============================================================
def detect_source_format(df: pd.DataFrame) -> str:
    """
    Detect source format by column signatures.

    Returns:
        "standard" | "propstream" | "batchleads" | "zillow" | "unknown"
    """
    cols_normalized = {_normalize(c) for c in df.columns}

    # Standard format — has our EXPECTED_COLUMNS
    expected_normalized = {_normalize(c) for c in EXPECTED_COLUMNS}
    if expected_normalized.issubset(cols_normalized):
        return "standard"

    # PropStream markers
    propstream_markers = {
        "owner first name", "owner last name", "property address",
        "for sale by owner",
    }
    if propstream_markers.issubset(cols_normalized):
        return "propstream"

    # BatchLeads markers
    batchleads_markers = {
        "owner name", "property street", "property city",
    }
    if batchleads_markers.issubset(cols_normalized):
        return "batchleads"

    # Zillow markers
    zillow_markers = {
        "owner 1 full name", "address", "city", "state",
    }
    if zillow_markers.issubset(cols_normalized):
        return "zillow"

    return "unknown"


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ADAPTER v2 — FLEXIBILITY TEST")
    print("=" * 60)

    # Test 1: PropStream-style
    print("\n[1] PropStream format:")
    df1 = pd.DataFrame({
        "Owner First Name": ["John"],
        "Owner Last Name": ["Smith"],
        "Property Address": ["123 Oak St"],
        "City": ["Dallas"],
        "State": ["TX"],
        "County Name": ["Dallas"],
        "Listing Price": ["185000"],
        "Original Price": ["195000"],
        "For Sale By Owner": ["Yes"],
        "Price Drop Flag": ["Yes"],
    })
    print(f"   Detected: {detect_source_format(df1)}")
    print(adapt_generic(df1).to_string(index=False))

    # Test 2: Case variations
    print("\n[2] Lowercase column names:")
    df2 = pd.DataFrame({
        "owner_first_name": ["Sarah"],
        "owner_last_name": ["Johnson"],
        "property_address": ["456 Pine Ave"],
        "city": ["Houston"],
        "state": ["TX"],
        "county": ["Harris"],
        "listing_price": ["450000"],
        "original_price": ["485000"],
        "for_sale_by_owner": ["No"],
        "price_drop": ["Yes"],
    })
    print(f"   Detected: {detect_source_format(df2)}")
    print(adapt_generic(df2).to_string(index=False))

    # Test 3: Full name + batchleads style
    print("\n[3] BatchLeads-style (full name):")
    df3 = pd.DataFrame({
        "Owner Name": ["David Wilson"],
        "Property Street": ["654 Cedar Ln"],
        "Property City": ["Plano"],
        "State": ["TX"],
        "County Name": ["Collin"],
        "Asking Price": ["120000"],
        "Original Price": ["135000"],
    })
    print(f"   Detected: {detect_source_format(df3)}")
    print(adapt_generic(df3).to_string(index=False))

    print("\n✅ All formats handled successfully!")
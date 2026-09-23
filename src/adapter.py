"""
ADAPTER LAYER (v3 — Flexible Column Mapping + Days/Type)
=========================================================
Converts external CSV formats into our standard format.

KEY FEATURES:
    - Case-insensitive column matching
    - Alias-based mapping (multiple names → one field)
    - Supports: PropStream, BatchLeads, Zillow, custom
    - Auto-format detection via column signatures
    - Clear error messages for unknown formats
    - v3: adds days_on_market + property_type (Fix 5)

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
    "days_on_market",    # NEW (Fix 5)
    "property_type",     # NEW (Fix 5)
    "distress_signals",
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
    # --- Full Name ---
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
    # --- Days on Market (NEW — Fix 5) ---
    "days_on_market": [
        "days on market", "dom", "days_on_market",
        "listing days", "days listed", "time on market",
        "days on mkt", "market days", "dom count",
        "days_on_mkt", "list days",
    ],
    # --- Property Type (NEW — Fix 5) ---
    "property_type": [
        "property type", "property_type", "type",
        "home type", "building type", "land use",
        "property category", "prop type", "propertytype",
        "property class", "asset type",
    ],
}


def _normalize(s: str) -> str:
    """Lowercase, strip, remove extra spaces and underscores."""
    if s is None:
        return ""
    return str(s).strip().lower().replace("_", " ").replace("-", " ")


def _build_lookup(df_columns: List[str]) -> Dict[str, str]:
    """Build a lookup: normalized_column → original_column."""
    lookup = {}
    for col in df_columns:
        normalized = _normalize(col)
        lookup[normalized] = col
    return lookup


def _find_column(df_columns: List[str], alias_key: str) -> Optional[str]:
    """Find the original column name matching any alias for `alias_key`."""
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
    f = _safe_str(first)
    l = _safe_str(last)
    if f or l:
        return f"{f} {l}".strip()
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
    return "price_drop"


def _safe_number(val, default=None):
    """Convert to float safely."""
    if pd.isna(val) or val is None or val == "":
        return default
    try:
        s = str(val).replace("$", "").replace(",", "").strip()
        return float(s)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=None):
    """Convert to int safely (for days_on_market)."""
    if pd.isna(val) or val is None or val == "":
        return default
    try:
        s = str(val).replace(",", "").strip()
        return int(float(s))
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
    dom_col = _find_column(cols, "days_on_market")   # NEW (Fix 5)
    ptype_col = _find_column(cols, "property_type")  # NEW (Fix 5)

    # Validate: need at least address
    if not street_col:
        raise ValueError(
            f"Could not find address column. Looked for: "
            f"{COLUMN_ALIASES['street'][:3]}...\n"
            f"Available columns: {cols}"
        )

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

    # Mailing address (optional)
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
        # ============================================================
       # ============================================================
    # Days on market + Property type (Fix 5 + Fix 6b)
    # ============================================================
    # Fix 6b: use list of None instead of scalar None so the column
    # is always created with correct length
    if dom_col:
        adapted["days_on_market"] = raw_df[dom_col].apply(_safe_int)
    else:
        adapted["days_on_market"] = [None] * len(raw_df)

    if ptype_col:
        adapted["property_type"] = raw_df[ptype_col].apply(_safe_str)
    else:
        adapted["property_type"] = [None] * len(raw_df)

    # ============================================================
    # Distress signals (row-wise — Fix 5 fixes scalar bug)
    # ============================================================
    # Build a per-row list of distress signals
    row_signals = []
    for _, row in raw_df.iterrows():
        signals_for_row = []
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
                val = str(row.get(col, "")).strip().lower()
                if val in ("yes", "y", "true", "1"):
                    signals_for_row.append(signal_name)

        row_signals.append(",".join(signals_for_row))

    adapted["distress_signals"] = row_signals

    # Force column order (Bug 3 fix: don't duplicate distress_signals)
    adapted = adapted[EXPECTED_COLUMNS]
    return adapted


# ============================================================
# BACKWARD-COMPAT
# ============================================================
def adapt_propstream(raw_df: pd.DataFrame) -> pd.DataFrame:
    """PropStream adapter — now uses universal adapter internally."""
    return adapt_generic(raw_df)


def load_from_propstream(file_path: str) -> pd.DataFrame:
    raw_df = pd.read_csv(file_path)
    return adapt_propstream(raw_df)


# ============================================================
# FORMAT DETECTION
# ============================================================
def detect_source_format(df: pd.DataFrame) -> str:
    """Detect source format by column signatures."""
    cols_normalized = {_normalize(c) for c in df.columns}

    # Standard format — has all required EXPECTED_COLUMNS
    required = {
        "owner_name", "address", "owner_mailing_address", "phone",
        "listing_type", "list_price", "previous_price", "county",
    }
    required_normalized = {_normalize(c) for c in required}
    if required_normalized.issubset(cols_normalized):
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
    print("ADAPTER v3 — Days/Type Test (Fix 5)")
    print("=" * 60)

    # Test 1: PropStream-style + days + type
    print("\n[1] PropStream format + days_on_market + property_type:")
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
        "Days on Market": ["45"],
        "Property Type": ["Single Family"],
        "Tax Delinquent": ["Yes"],
    })
    out1 = adapt_generic(df1)
    print(out1.to_string(index=False))

    # Test 2: Missing days/type → should be None/blank
    print("\n[2] No days/type columns (should be None/blank):")
    df2 = pd.DataFrame({
        "owner_first_name": ["Sarah"],
        "owner_last_name": ["Johnson"],
        "property_address": ["456 Pine Ave"],
        "city": ["Houston"],
        "state": ["TX"],
        "county": ["Harris"],
        "listing_price": ["450000"],
        "original_price": ["485000"],
    })
    out2 = adapt_generic(df2)
    print(out2.to_string(index=False))

    print("\n✅ Adapter v3 test complete")
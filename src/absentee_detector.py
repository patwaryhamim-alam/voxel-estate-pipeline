"""
ABSENTEE OWNER DETECTOR (v2 — with edge cases)
==============================================
Determines if a property owner lives at the property or elsewhere.

EDGE CASES HANDLED:
    - PO Box mailing addresses
    - Blank / missing mailing address
    - LLC / Trust / Corp owner names (always absentee)
    - City-only mailing addresses
    - Same street in different cities
    - Missing ZIP codes

OUTPUT STATUSES:
    - owner_occupied        → lives at property
    - in_state_absentee     → same state, different city
    - out_of_state_absentee → different state (hottest lead)
    - llc_or_trust_owner    → business-owned (always absentee)
    - unknown               → insufficient data
"""

import re


# ============================================================
# US STATE CODES + FULL NAMES
# ============================================================
VALID_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

STATE_NAME_TO_CODE = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT",
    "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI",
    "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA",
    "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME",
    "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
    "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO",
    "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM",
    "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND",
    "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC",
}

# Business entity indicators (always absentee)
BUSINESS_ENTITY_KEYWORDS = [
    "LLC", "L.L.C.", "INC", "INC.", "CORP", "CORPORATION",
    "TRUST", "TRUSTEE", "LP", "L.P.", "LLP", "COMPANY",
    "CO.", "ENTERPRISES", "PROPERTIES", "HOLDINGS",
    "INVESTMENTS", "REALTY", "REAL ESTATE", "PARTNERS",
    "PARTNERSHIP", "ESTATE OF", "FAMILY TRUST", "REVOCABLE TRUST",
]


# ============================================================
# HELPERS
# ============================================================
def _is_po_box(address: str) -> bool:
    """Check if address contains a PO Box."""
    if not address:
        return False
    return bool(re.search(r"\bP\.?\s*O\.?\s*BOX\b", str(address).upper()))


def _is_business_entity(name: str) -> bool:
    """Check if owner name indicates a business entity."""
    if not name:
        return False
    upper = str(name).upper()
    return any(kw in upper for kw in BUSINESS_ENTITY_KEYWORDS)


def _has_street_number(address: str) -> bool:
    """Check if address starts with a street number."""
    if not address:
        return False
    return bool(re.search(r"^\s*\d+", str(address)))


def _extract_state(address: str):
    """Find 2-letter state code in address string."""
    if not address:
        return None

    upper = str(address).strip().upper()
    words = re.split(r"[\s,]+", upper)

    # Try 2-letter codes (from end)
    for word in reversed(words):
        if word in VALID_US_STATES:
            return word

    # Try full state names
    for name, code in STATE_NAME_TO_CODE.items():
        if name in upper:
            return code

    return None


def _extract_city(address: str):
    """Naive city extraction."""
    if not address:
        return None

    addr = str(address).strip()

    # Comma-based: "123 Oak St, Dallas, TX"
    if "," in addr:
        parts = [p.strip() for p in addr.split(",")]
        for i in range(len(parts) - 1, -1, -1):
            if _extract_state(parts[i]):
                if i > 0:
                    return parts[i - 1].upper()
                break

    # Word-based fallback
    words = addr.split()
    for i, word in enumerate(words):
        if word.upper() in VALID_US_STATES or word.upper() in STATE_NAME_TO_CODE:
            if i > 0:
                return words[i - 1].upper()

    return None


# ============================================================
# MAIN DETECTOR
# ============================================================
def detect_absentee(property_address, mailing_address, owner_name=None):
    """
    Detect absentee owner status.

    Args:
        property_address: Where the property sits
        mailing_address:  Where owner receives mail
        owner_name:       Optional — for LLC/Trust detection

    Returns:
        (status: str, reason: str)
    """
    # ============================================================
    # EDGE CASE 1: Business entity owner (always absentee)
    # ============================================================
    if owner_name and _is_business_entity(owner_name):
        # Try to determine if we can still detect location
        prop_state = _extract_state(property_address)
        mail_state = _extract_state(mailing_address)

        if prop_state and mail_state and prop_state != mail_state:
            return (
                "out_of_state_absentee",
                f"Business entity ({owner_name[:30]}), located out-of-state",
            )
        return (
            "llc_or_trust_owner",
            f"Business/Trust entity ({owner_name[:30]}) — always absentee",
        )

    # ============================================================
    # EDGE CASE 2: Missing addresses
    # ============================================================
    if not property_address or not mailing_address:
        return "unknown", "Missing property or mailing address"

    # ============================================================
    # EDGE CASE 3: PO Box mailing (can't determine owner location)
    # ============================================================
    if _is_po_box(mailing_address):
        prop_state = _extract_state(property_address)
        mail_state = _extract_state(mailing_address)

        if prop_state and mail_state and prop_state != mail_state:
            return (
                "out_of_state_absentee",
                f"PO Box in {mail_state}, property in {prop_state}",
            )
        elif prop_state and mail_state and prop_state == mail_state:
            return (
                "in_state_absentee",
                "PO Box mailing address (in-state)",
            )
        return "unknown", "PO Box — cannot determine location"

    # ============================================================
    # EDGE CASE 4: Normal state-based comparison
    # ============================================================
    prop_state = _extract_state(property_address)
    mail_state = _extract_state(mailing_address)

    if not prop_state or not mail_state:
        return "unknown", "Could not extract state from addresses"

    # Different state → out-of-state (hottest)
    if prop_state != mail_state:
        return (
            "out_of_state_absentee",
            f"Owner lives in {mail_state}, property in {prop_state}",
        )

    # Same state, different city → in-state absentee
    prop_city = _extract_city(property_address)
    mail_city = _extract_city(mailing_address)

    if not prop_city or not mail_city:
        return (
            "in_state_absentee",
            f"Same state ({mail_state}) — city unknown",
        )

    if prop_city != mail_city:
        return (
            "in_state_absentee",
            f"Owner in {mail_city}, property in {prop_city}",
        )

    # Same state + city → likely owner-occupied
    return (
        "owner_occupied",
        f"Owner lives at property ({prop_city}, {prop_state})",
    )


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 75)
    print("ABSENTEE DETECTOR v2 — EDGE CASE TEST")
    print("=" * 75)

    test_cases = [
        # (property, mailing, owner_name, expected)
        ("123 Oak St, Dallas, TX", "123 Oak St, Dallas, TX", "John Smith",
         "owner_occupied"),

        ("123 Oak St, Dallas, TX", "456 Pine, Houston, TX", "Sarah Johnson",
         "in_state_absentee"),

        ("147 Walnut Way, Austin, TX", "888 Lake, Phoenix, AZ", "Robert Taylor",
         "out_of_state_absentee"),

        # PO Box cases
        ("123 Oak St, Dallas, TX", "PO Box 123, Dallas, TX", "John Smith",
         "in_state_absentee"),

        ("123 Oak St, Dallas, TX", "PO Box 123, Phoenix, AZ", "John Smith",
         "out_of_state_absentee"),

        # Business entity
        ("123 Oak St, Dallas, TX", "500 Business, Dallas, TX",
         "Smith Family Trust", "llc_or_trust_owner"),

        ("123 Oak St, Dallas, TX", "500 Business, Phoenix, AZ",
         "ABC Properties LLC", "out_of_state_absentee"),

        # Missing data
        ("123 Oak St, Dallas, TX", "", "John Smith", "unknown"),

        ("", "456 Pine, Houston, TX", "John Smith", "unknown"),

        # City-only mailing
        ("123 Oak St, Dallas, TX", "Houston, TX", "John Smith",
         "in_state_absentee"),
    ]

    pass_count = 0
    for i, (prop, mail, owner, expected) in enumerate(test_cases, 1):
        status, reason = detect_absentee(prop, mail, owner)
        ok = status == expected
        marker = "✅ PASS" if ok else "❌ FAIL"
        if ok:
            pass_count += 1

        print(f"\n[{i}] {marker}")
        print(f"    Property: {prop}")
        print(f"    Mailing:  {mail}")
        print(f"    Owner:    {owner}")
        print(f"    Result:   {status}")
        print(f"    Reason:   {reason}")
        if not ok:
            print(f"    Expected: {expected}")

    print("\n" + "=" * 75)
    print(f"  RESULT: {pass_count}/{len(test_cases)} tests passed")
    print("=" * 75)
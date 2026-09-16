"""
ABSENTEE OWNER DETECTOR (US-Only)
=================================
Determines if a property owner lives at the property (owner-occupied)
or elsewhere (absentee).

Absentee owners = HIGH-VALUE leads:
    - Can't maintain the property
    - More likely motivated sellers
    - Often open to offers

DETECTION LOGIC:
    Compare property address vs owner mailing address.
    - Same city + same state -> owner_occupied
    - Same state, different city -> in_state_absentee
    - Different state -> out_of_state_absentee
    - Missing data -> unknown

USAGE:
    from absentee_detector import detect_absentee
    status, reason = detect_absentee(
        "123 Oak St, Dallas, TX",
        "456 Pine Ave, Houston, TX"
    )
    # status -> "in_state_absentee"
    # reason -> "Lives in HOUSTON, property in DALLAS"
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


# ============================================================
# ADDRESS PARSING HELPERS
# ============================================================
def _extract_state(address):
    """Find the 2-letter state code in an address string."""
    if not address:
        return None

    upper = str(address).strip().upper()

    # Try 2-letter code first (word-boundary match)
    words = re.split(r"[\s,]+", upper)
    for word in reversed(words):
        if word in VALID_US_STATES:
            return word

    # Try full state names
    for name, code in STATE_NAME_TO_CODE.items():
        if name in upper:
            return code

    return None


def _extract_city(address):
    """
    Naive city extraction:
        1. Split by comma -> if last part has state, city = 2nd-to-last
        2. Otherwise, take word before the state code
    """
    if not address:
        return None

    addr = str(address).strip()

    # Try comma-based parsing
    if "," in addr:
        parts = [p.strip() for p in addr.split(",")]
        # Example: "123 Oak St, Dallas, TX" -> ["123 Oak St", "Dallas", "TX"]
        for i in range(len(parts) - 1, -1, -1):
            if _extract_state(parts[i]):
                if i > 0:
                    return parts[i - 1].upper()
                break

    # Fallback: word before state
    words = addr.split()
    for i, word in enumerate(words):
        if word.upper() in VALID_US_STATES or word.upper() in STATE_NAME_TO_CODE:
            if i > 0:
                return words[i - 1].upper()

    return None


# ============================================================
# MAIN DETECTOR
# ============================================================
def detect_absentee(property_address, mailing_address):
    """
    Detect absentee owner status.

    Args:
        property_address: The property's full address (where it sits)
        mailing_address:  Owner's mailing address (where they live)

    Returns:
        (status: str, reason: str)
        status one of:
            "owner_occupied"        - lives at property
            "in_state_absentee"     - same state, different city
            "out_of_state_absentee" - lives in another state
            "unknown"               - missing data / can't parse
    """
    if not property_address or not mailing_address:
        return "unknown", "Missing property or mailing address"

    prop_state = _extract_state(property_address)
    mail_state = _extract_state(mailing_address)

    if not prop_state or not mail_state:
        return "unknown", "Could not extract state from addresses"

    if prop_state != mail_state:
        return (
            "out_of_state_absentee",
            f"Owner lives in {mail_state}, property in {prop_state}",
        )

    # Same state — check city
    prop_city = _extract_city(property_address)
    mail_city = _extract_city(mailing_address)

    if not prop_city or not mail_city:
        return (
            "in_state_absentee",
            f"Owner in {mail_state}, exact city unknown",
        )

    if prop_city != mail_city:
        return (
            "in_state_absentee",
            f"Owner lives in {mail_city}, property in {prop_city}",
        )

    return (
        "owner_occupied",
        f"Owner lives at property ({prop_city}, {prop_state})",
    )


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 75)
    print("  ABSENTEE OWNER DETECTOR — TEST RUN")
    print("=" * 75)

    test_cases = [
        # (property, mailing, expected_status)
        (
            "123 Oak St, Dallas, TX",
            "123 Oak St, Dallas, TX",
            "owner_occupied",
        ),
        (
            "123 Oak St, Dallas, TX",
            "456 Pine Ave, Houston, TX",
            "in_state_absentee",
        ),
        (
            "147 Walnut Way, Austin, TX",
            "888 Lake View Dr, Phoenix, AZ",
            "out_of_state_absentee",
        ),
        (
            "555 Elm St, Austin, TX 78703",
            "555 Elm St, Austin, TX 78703",
            "owner_occupied",
        ),
        (
            "123 Oak St Dallas TX",
            "456 Pine Ave Houston TX",
            "in_state_absentee",
        ),
        (
            "123 Main St, Dallas, TX",
            "",
            "unknown",
        ),
        (
            "123 Main St",
            "456 Other St, CA",
            "unknown",
        ),
    ]

    pass_count = 0
    for i, (prop, mail, expected) in enumerate(test_cases, 1):
        status, reason = detect_absentee(prop, mail)
        ok = status == expected
        marker = "PASS" if ok else "FAIL"
        if ok:
            pass_count += 1
        print(f"\n[{i}] [{marker}]")
        print(f"    Property : {prop}")
        print(f"    Mailing  : {mail}")
        print(f"    Result   : {status}")
        print(f"    Reason   : {reason}")
        if not ok:
            print(f"    Expected : {expected}")

    print("\n" + "=" * 75)
    print(f"  RESULT: {pass_count}/{len(test_cases)} tests passed")
    print("=" * 75)
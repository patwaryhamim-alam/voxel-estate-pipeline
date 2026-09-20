"""
US DATA VALIDATORS (v2)
=======================
US-market validation utilities.

IMPROVED IN v2:
    - Phone extensions stripped (ext. 123, x123, #123)
    - Multiple phone numbers handled (take first valid)
    - Country code +1 handled
    - Better edge case coverage
"""

import re
from datetime import datetime


# ============================================================
# US STATES
# ============================================================
VALID_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


# ============================================================
# PHONE VALIDATION (v2)
# ============================================================
def validate_phone(phone):
    """
    Validate a US phone number (10 digits).

    Handles:
        (555) 123-4567
        555-123-4567
        555.123.4567
        5551234567
        +1 555 123 4567
        1-555-123-4567
        555-123-4567 ext. 123      → strips extension
        555-123-4567 x123          → strips extension
        555-123-4567; 555-987-6543 → takes first

    Returns:
        (is_valid: bool, cleaned: str, reason: str)
    """
    if phone is None or str(phone).strip() == "":
        return False, "", "Phone is empty"

    phone_str = str(phone).strip()

    # Strip multiple numbers — take first
    # Separators: ; / , | or "or"
    first_number = re.split(r"[;/|]|\s+or\s+", phone_str, maxsplit=1)[0]
    first_number = first_number.strip()

    # Strip extension patterns
    # "ext. 123", "ext 123", "x123", "#123", "extension 123"
    first_number = re.sub(
        r"\s*(?:ext\.?|extension|x|#)\s*\d+\s*$",
        "",
        first_number,
        flags=re.IGNORECASE,
    ).strip()

    # Strip all non-digits
    digits = re.sub(r"\D", "", first_number)

    # Remove leading "1" if US country code
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    # Must be exactly 10 digits
    if len(digits) != 10:
        return False, digits, f"Expected 10 digits, got {len(digits)}"

    # Area code cannot start with 0 or 1
    if digits[0] in "01":
        return False, digits, "Area code cannot start with 0 or 1"

    # Exchange code (digits 4-6) cannot start with 0 or 1
    if digits[3] in "01":
        return False, digits, "Exchange code cannot start with 0 or 1"

    return True, digits, "OK"


def format_phone(phone):
    """Format phone as (XXX) XXX-XXXX."""
    ok, digits, _ = validate_phone(phone)
    if not ok:
        return None
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


# ============================================================
# ZIP VALIDATION
# ============================================================
def validate_zip(zip_code):
    """Validate a US ZIP code (5 or 9 digits)."""
    if zip_code is None or str(zip_code).strip() == "":
        return False, "", "ZIP is empty"

    digits = re.sub(r"\D", "", str(zip_code))

    if len(digits) == 5:
        return True, digits, "OK"
    if len(digits) == 9:
        return True, f"{digits[:5]}-{digits[5:]}", "OK (ZIP+4)"

    return False, digits, f"ZIP must be 5 or 9 digits, got {len(digits)}"


# ============================================================
# STATE VALIDATION
# ============================================================
def validate_state(state):
    """Validate a US state code (2 letters)."""
    if state is None or str(state).strip() == "":
        return False, "", "State is empty"

    code = str(state).strip().upper()
    if len(code) != 2:
        return False, code, f"State code must be 2 letters, got '{code}'"
    if code not in VALID_US_STATES:
        return False, code, f"'{code}' is not a valid US state"

    return True, code, "OK"


# ============================================================
# ADDRESS VALIDATION
# ============================================================
def validate_address(address):
    """Basic US address validation."""
    if not address or str(address).strip() == "":
        return False, "Address is empty"

    addr = str(address).strip()
    if not re.search(r"\d", addr):
        return False, "Address has no street number"
    if len(addr.split()) < 2:
        return False, "Address too short"

    return True, "OK"


# ============================================================
# USD CURRENCY
# ============================================================
def format_usd(amount, with_cents=False):
    """Format a number as USD."""
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return None

    if with_cents:
        return f"${amount:,.2f}"
    return f"${amount:,.0f}"


# ============================================================
# US DATE
# ============================================================
def format_us_date(date_obj=None):
    """Format date as MM/DD/YYYY."""
    if date_obj is None:
        date_obj = datetime.now()
    if isinstance(date_obj, str):
        return date_obj
    return date_obj.strftime("%m/%d/%Y")


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  US VALIDATORS v2 — TEST RUN")
    print("=" * 70)

    print("\n[1] Phone validation (with edge cases):")
    test_phones = [
        "(555) 123-4567",
        "555-123-4567 ext. 123",
        "555-123-4567 x123",
        "555.123.4567",
        "5551234567",
        "+1 555 123 4567",
        "1-555-123-4567",
        "555-123-4567; 555-987-6543",   # Multiple
        "555-123-4567 or 555-987-6543", # Multiple
        "555-123-4567, ext 22",
        "123",
        "055-123-4567",
        "",
    ]
    for p in test_phones:
        ok, cleaned, reason = validate_phone(p)
        status = "PASS" if ok else "REJECT"
        print(f"   [{status}] {repr(p):40} -> {cleaned:15} ({reason})")

    print("\n[2] Phone formatting:")
    print(f"   format_phone('5551234567') -> {format_phone('5551234567')}")
    print(f"   format_phone('555-123-4567 ext 99') -> {format_phone('555-123-4567 ext 99')}")

    print("\n[3] State validation:")
    for s in ["TX", "CA", "tx", "XX", "TEXAS", ""]:
        ok, cleaned, reason = validate_state(s)
        status = "PASS" if ok else "REJECT"
        print(f"   [{status}] {repr(s):10} -> {cleaned:5} ({reason})")

    print("\n✅ Test complete")
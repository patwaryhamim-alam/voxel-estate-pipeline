"""
US DATA VALIDATORS
==================
US-market-specific validation utilities for the pipeline.

USAGE:
    from us_validators import validate_phone, validate_zip, format_usd
    ok, cleaned = validate_phone("(555) 123-4567")
    print(ok, cleaned)  # True, "5551234567"
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
# PHONE VALIDATION
# ============================================================
def validate_phone(phone):
    """
    Validate a US phone number (10 digits).

    Accepts formats:
        (555) 123-4567
        555-123-4567
        555.123.4567
        5551234567
        +1 555 123 4567
        1-555-123-4567

    Returns:
        (is_valid: bool, cleaned: str, reason: str)
        cleaned = "5551234567" (digits only)
    """
    if phone is None or str(phone).strip() == "":
        return False, "", "Phone is empty"

    # Strip all non-digits
    digits = re.sub(r"\D", "", str(phone))

    # Remove leading "1" if present (US country code)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) != 10:
        return False, digits, f"Expected 10 digits, got {len(digits)}"

    # Area code cannot start with 0 or 1
    if digits[0] in "01":
        return False, digits, "Area code cannot start with 0 or 1"

    return True, digits, "OK"


def format_phone(phone):
    """Format a US phone number as (XXX) XXX-XXXX."""
    ok, digits, _ = validate_phone(phone)
    if not ok:
        return None
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


# ============================================================
# ZIP CODE VALIDATION
# ============================================================
def validate_zip(zip_code):
    """
    Validate a US ZIP code.

    Accepts:
        12345
        12345-6789
        123456789

    Returns:
        (is_valid: bool, cleaned: str, reason: str)
    """
    if zip_code is None or str(zip_code).strip() == "":
        return False, "", "ZIP is empty"

    # Strip non-digits
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
    """
    Basic US address validation.
    Checks: has street number, city, state reference.
    """
    if not address or str(address).strip() == "":
        return False, "Address is empty"

    addr = str(address).strip()

    # Must have a digit (street number)
    if not re.search(r"\d", addr):
        return False, "Address has no street number"

    # Should have at least 2 words
    if len(addr.split()) < 2:
        return False, "Address too short"

    return True, "OK"


# ============================================================
# USD CURRENCY FORMAT
# ============================================================
def format_usd(amount, with_cents=False):
    """
    Format a number as USD.
        format_usd(185000) -> "$185,000"
        format_usd(185000.50, with_cents=True) -> "$185,000.50"
    """
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return None

    if with_cents:
        return f"${amount:,.2f}"
    return f"${amount:,.0f}"


# ============================================================
# US DATE FORMAT
# ============================================================
def format_us_date(date_obj=None):
    """Format date as MM/DD/YYYY (US style)."""
    if date_obj is None:
        date_obj = datetime.now()
    if isinstance(date_obj, str):
        return date_obj  # already string
    return date_obj.strftime("%m/%d/%Y")


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  US VALIDATORS — TEST RUN")
    print("=" * 70)

    # Phone tests
    print("\n[1] Phone validation:")
    test_phones = [
        "(555) 123-4567",
        "555-123-4567",
        "555.123.4567",
        "5551234567",
        "+1 555 123 4567",
        "1-555-123-4567",
        "123",              # too short
        "055-123-4567",     # invalid area code
        "",                 # empty
    ]
    for p in test_phones:
        ok, cleaned, reason = validate_phone(p)
        status = "PASS" if ok else "REJECT"
        print(f"   [{status}] {repr(p):25} -> {cleaned:15} ({reason})")

    # Format test
    print("\n[2] Phone formatting:")
    print(f"   format_phone('5551234567') -> {format_phone('5551234567')}")

    # ZIP tests
    print("\n[3] ZIP validation:")
    test_zips = ["12345", "12345-6789", "123456789", "123", "ABCDE"]
    for z in test_zips:
        ok, cleaned, reason = validate_zip(z)
        status = "PASS" if ok else "REJECT"
        print(f"   [{status}] {repr(z):20} -> {cleaned:15} ({reason})")

    # State tests
    print("\n[4] State validation:")
    test_states = ["TX", "CA", "tx", "XX", "TEXAS", ""]
    for s in test_states:
        ok, cleaned, reason = validate_state(s)
        status = "PASS" if ok else "REJECT"
        print(f"   [{status}] {repr(s):10} -> {cleaned:5} ({reason})")

    # Address tests
    print("\n[5] Address validation:")
    test_addresses = [
        "123 Oak St Dallas TX",
        "Oak St",           # no number
        "12",               # too short
        "",                 # empty
    ]
    for a in test_addresses:
        ok, reason = validate_address(a)
        status = "PASS" if ok else "REJECT"
        print(f"   [{status}] {repr(a):25} -> {reason}")

    # USD format
    print("\n[6] USD formatting:")
    print(f"   format_usd(185000)         -> {format_usd(185000)}")
    print(f"   format_usd(185000.50)      -> {format_usd(185000.50)}")
    print(f"   format_usd(185000.50,True) -> {format_usd(185000.50, True)}")

    # Date format
    print("\n[7] US date format:")
    print(f"   format_us_date() -> {format_us_date()}")

    print("\n" + "=" * 70)
    print("  ✅ All tests complete")
    print("=" * 70)
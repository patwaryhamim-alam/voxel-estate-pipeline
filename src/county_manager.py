"""
COUNTY EXCLUSIVITY MANAGER (US-Only)
====================================
Tracks which US clients belong to which counties.
Enforces: max 3 clients per county.

US-ONLY VALIDATION:
    - Only 50 US states + DC allowed
    - County format: county_name_state_code (e.g., maricopa_az)
    - Non-US counties are rejected

USAGE:
    from county_manager import CountyManager
    cm = CountyManager()
    ok, msg = cm.add_client("maricopa_az", "client_001", "John Doe")
"""

import json
from datetime import datetime
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================
CLIENTS_FILE = Path("data/clients.json")
MAX_CLIENTS_PER_COUNTY = 3

# US States (50 states + DC)
VALID_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


# ============================================================
# US VALIDATION
# ============================================================
def _validate_us_county(county_str):
    """
    Verify a county string is in US format.
    Format: county_name_state_code (e.g., maricopa_az)
    """
    county_str = county_str.lower().strip()
    if "_" not in county_str:
        return False, f"Invalid format. Use 'county_name_state' (e.g., maricopa_az)"

    parts = county_str.split("_")
    if len(parts) < 2:
        return False, f"Invalid format: {county_str}"

    state_code = parts[-1].upper()
    if state_code not in VALID_US_STATES:
        return False, f"'{state_code}' is not a valid US state code"

    return True, "OK"


# ============================================================
# COUNTY MANAGER
# ============================================================
class CountyManager:
    """Manages county-to-client assignments (US-only)."""

    def __init__(self, file_path=None):
        self.file_path = Path(file_path) if file_path else CLIENTS_FILE
        self._load()

    def _load(self):
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"'{self.file_path}' pawa jay ni. data/ folder check koro."
            )
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def _save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # --------------------------------------------------------
    def is_available(self, county):
        """Check if county has space for more clients."""
        county = county.lower().strip()

        # US validation
        is_valid, msg = _validate_us_county(county)
        if not is_valid:
            return False, f"US validation failed: {msg}"

        if county not in self.data:
            return False, f"County '{county}' is not in supported list"

        current = len(self.data[county])
        if current >= MAX_CLIENTS_PER_COUNTY:
            return False, f"County '{county}' is FULL ({current}/{MAX_CLIENTS_PER_COUNTY})"

        return True, f"{MAX_CLIENTS_PER_COUNTY - current} spot(s) available"

    def add_client(self, county, client_id, client_name, email=""):
        """Add a client to a county. Fails if county is full or invalid."""
        county = county.lower().strip()

        # US validation
        is_valid, msg = _validate_us_county(county)
        if not is_valid:
            return False, f"US validation failed: {msg}"

        if county not in self.data:
            return False, f"County '{county}' not supported. Add it first."

        if len(self.data[county]) >= MAX_CLIENTS_PER_COUNTY:
            return False, f"County '{county}' is FULL ({MAX_CLIENTS_PER_COUNTY}/{MAX_CLIENTS_PER_COUNTY})"

        for existing in self.data[county]:
            if existing.get("id") == client_id:
                return False, f"Client '{client_id}' already exists in {county}"

        self.data[county].append({
            "id": client_id,
            "name": client_name,
            "email": email,
            "joined": datetime.now().strftime("%Y-%m-%d"),
        })
        self._save()
        return True, f"Added '{client_name}' to {county} ({len(self.data[county])}/{MAX_CLIENTS_PER_COUNTY})"

    def remove_client(self, county, client_id):
        """Remove a client (e.g., if they cancel)."""
        county = county.lower().strip()
        if county not in self.data:
            return False, f"County '{county}' not found"

        before = len(self.data[county])
        self.data[county] = [c for c in self.data[county] if c.get("id") != client_id]
        after = len(self.data[county])

        if before == after:
            return False, f"Client '{client_id}' not found in {county}"

        self._save()
        return True, f"Removed '{client_id}' from {county} ({after}/{MAX_CLIENTS_PER_COUNTY})"

    def list_counties(self):
        return list(self.data.keys())

    def get_county_clients(self, county):
        return self.data.get(county.lower().strip(), [])

    def print_status(self):
        """Print a full status report."""
        print("=" * 70)
        print("  COUNTY EXCLUSIVITY STATUS (US-Only)")
        print("=" * 70)
        for county, clients in self.data.items():
            count = len(clients)
            status = "OK" if count < MAX_CLIENTS_PER_COUNTY else "FULL"
            print(f"\n{county.upper()}  [{count}/{MAX_CLIENTS_PER_COUNTY}]  [{status}]")
            if clients:
                for c in clients:
                    print(f"   - {c['id']:15} | {c['name']:20} | joined {c.get('joined', 'N/A')}")
            else:
                print(f"   (no clients yet)")
        print("\n" + "=" * 70)


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  COUNTY MANAGER — TEST RUN (US-Only)")
    print("=" * 70)

    cm = CountyManager()

    # 1. Initial status
    print("\n[1] Initial status:")
    cm.print_status()

    # 2. Availability check
    print("\n[2] Checking 'maricopa_az':")
    ok, msg = cm.is_available("maricopa_az")
    print(f"   {msg}")

    # 3. US validation tests
    print("\n[3] US validation tests:")
    test_counties = [
        "maricopa_az",      # Valid
        "mumbai_in",        # Invalid state
        "london_uk",        # Invalid state
        "invalidcounty",    # No state code
        "harris_tx",        # Valid
    ]
    for county in test_counties:
        is_valid, msg = _validate_us_county(county)
        status = "PASS" if is_valid else "REJECT"
        print(f"   [{status}] {county:20} -> {msg}")

    # 4. Add 3 test clients
    print("\n[4] Adding 3 clients to 'maricopa_az':")
    for i in range(1, 4):
        ok, msg = cm.add_client(
            "maricopa_az",
            f"test_client_{i:03d}",
            f"Test Client {i}",
        )
        print(f"   {msg}")

    # 5. Try 4th client (should fail)
    print("\n[5] Trying 4th client (should FAIL):")
    ok, msg = cm.add_client("maricopa_az", "test_client_004", "Test Client 4")
    print(f"   {msg}")

    # 6. Updated status
    print("\n[6] Updated status:")
    cm.print_status()

    # 7. Cleanup
    print("\n[7] Cleaning up test clients:")
    for i in range(1, 4):
        ok, msg = cm.remove_client("maricopa_az", f"test_client_{i:03d}")
        print(f"   {msg}")

    print("\n✅ Test complete.")
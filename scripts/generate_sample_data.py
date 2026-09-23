"""
Generate realistic real estate lead CSVs for testing.

FIX 1: Now includes edge cases:
    - LLC/Trust owners (~5%)
    - Missing previous_price (~8%)
    - Price increase (previous < list, ~5%)
    - Missing distress (~60%)
    - Distress signals (tax_delinquent, vacant, pre_foreclosure, etc.)
    - days_on_market, property_type columns
"""

import random
from pathlib import Path

import pandas as pd


FIRST_NAMES = [
    "John", "Sarah", "Michael", "Emily", "David", "Jennifer", "Robert", "Lisa",
    "James", "Mary", "William", "Patricia", "Richard", "Linda", "Joseph",
    "Barbara", "Thomas", "Elizabeth", "Charles", "Susan", "Daniel", "Jessica",
    "Matthew", "Karen", "Anthony", "Nancy", "Mark", "Betty", "Donald",
    "Margaret", "Steven", "Sandra", "Paul", "Ashley", "Andrew", "Kimberly",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen",
]

BUSINESS_SUFFIXES = [
    "LLC", "Properties LLC", "Holdings LLC", "Trust", "Family Trust",
    "Investments LLC", "Capital LLC", "Realty Trust", "Group LLC",
]

CITIES = [
    ("Phoenix", "Maricopa", "AZ", 180000, 550000),
    ("Houston", "Harris", "TX", 150000, 480000),
    ("Dallas", "Dallas", "TX", 180000, 520000),
    ("Austin", "Travis", "TX", 250000, 750000),
    ("Plano", "Collin", "TX", 220000, 600000),
    ("Tampa", "Hillsborough", "FL", 200000, 550000),
    ("Atlanta", "Fulton", "GA", 200000, 600000),
    ("Charlotte", "Mecklenburg", "NC", 220000, 550000),
    ("Nashville", "Davidson", "TN", 220000, 580000),
    ("Memphis", "Shelby", "TN", 130000, 380000),
]

STREET_NAMES = [
    "Oak", "Maple", "Pine", "Cedar", "Elm", "Washington", "Lake", "Hill",
    "Park", "Walnut", "Sunset", "Ridge", "Main", "Highland", "Forest",
]

STREET_TYPES = ["St", "Ave", "Rd", "Ln", "Dr", "Ct", "Way", "Blvd", "Pl"]

PROPERTY_TYPES = [
    "Single Family", "Single Family", "Single Family",
    "Condo", "Multi-Family", "Townhouse", "Duplex",
]

DISTRESS_SIGNALS = [
    "", "", "", "", "",  # 60% none
    "tax_delinquent",
    "vacant",
    "pre_foreclosure",
    "expired_listing",
    "divorce",
    "probate",
    "tax_delinquent,vacant",
]


def random_phone():
    area = random.choice(["214", "305", "404", "469", "512", "602", "615",
                          "713", "786", "813", "901", "919"])
    exchange = random.randint(200, 999)
    number = random.randint(1000, 9999)
    return f"({area}) {exchange}-{number}"


def random_street_address():
    number = random.randint(100, 9999)
    name = random.choice(STREET_NAMES)
    stype = random.choice(STREET_TYPES)
    return f"{number} {name} {stype}"


def generate_lead():
    city, county, state, min_p, max_p = random.choice(CITIES)

    # Owner name — 5% business entity
    if random.random() < 0.05:
        first = random.choice(LAST_NAMES)
        owner_name = f"{first} {random.choice(BUSINESS_SUFFIXES)}"
    else:
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        owner_name = f"{first} {last}"

    # Property address
    property_address = f"{random_street_address()} {city} {state}"

    # Mailing address — 30% out-of-state, 20% in-state absentee, 50% same
    r = random.random()
    if r < 0.30:
        other = [c for c in CITIES if c[2] != state]
        if other:
            mc, _, ms, _, _ = random.choice(other)
            mailing = f"{random_street_address()} {mc} {ms}"
        else:
            mailing = property_address
    elif r < 0.50:
        same_state = [c for c in CITIES if c[2] == state and c[0] != city]
        if same_state:
            mc, _, _, _, _ = random.choice(same_state)
            mailing = f"{random_street_address()} {mc} {state}"
        else:
            mailing = property_address
    else:
        mailing = property_address

    # Listing type
    listing_type = random.choice(["FSBO", "price_drop", "FSBO", "price_drop"])

    # Price — 5% increase, 8% missing previous, 87% normal drop
    list_price = round(random.randint(min_p, max_p) / 1000) * 1000

    roll = random.random()
    if roll < 0.05:  # 5% price INCREASE
        previous_price = int(list_price * random.uniform(0.90, 0.98))
        previous_price = round(previous_price / 1000) * 1000
    elif roll < 0.13:  # 8% missing previous
        previous_price = None
    else:  # 87% normal drop
        drop_pct = random.uniform(0.03, 0.22)
        previous_price = int(list_price / (1 - drop_pct))
        previous_price = round(previous_price / 1000) * 1000

    # Distress
    distress = random.choice(DISTRESS_SIGNALS)

    # Extra fields
    days_on_market = random.randint(5, 200)
    property_type = random.choice(PROPERTY_TYPES)

    # Phone
    phone = "" if random.random() < 0.10 else random_phone()

    return {
        "owner_name": owner_name,
        "address": property_address,
        "owner_mailing_address": mailing,
        "phone": phone,
        "listing_type": listing_type,
        "list_price": list_price,
        "previous_price": previous_price,
        "county": county,
        "distress_signals": distress,
        "days_on_market": days_on_market,
        "property_type": property_type,
    }


def main():
    random.seed(42)
    rows = [generate_lead() for _ in range(100)]
    df = pd.DataFrame(rows)

    output_path = Path("data/sample_100_leads.csv")
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"Generated {len(df)} leads -> {output_path}")
    print(f"  LLC/Trust: {(df['owner_name'].str.contains('LLC|Trust|Corp', na=False)).sum()}")
    print(f"  Missing prev_price: {df['previous_price'].isna().sum()}")
    print(f"  Price increase: {(df['previous_price'].notna() & (df['previous_price'] < df['list_price'])).sum()}")
    print(f"  With distress: {(df['distress_signals'] != '').sum()}")
    print(f"  Missing phone: {(df['phone'] == '').sum()}")


if __name__ == "__main__":
    main()
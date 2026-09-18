"""
Generate 100 realistic real estate leads for demo/screenshot purposes.

USES REAL-LOOKING:
    - US city/state combinations
    - Real street names
    - Realistic phone numbers
    - Real owner names
    - Real price ranges per market
    - Real FSBO/price-drop mix
    - 30% out-of-state absentee owners
"""

import random
from datetime import datetime
from pathlib import Path

import pandas as pd


# ============================================================
# DATA SOURCES — REAL-LOOKING US DATA
# ============================================================
FIRST_NAMES = [
    "John", "Sarah", "Michael", "Emily", "David", "Jennifer", "Robert", "Lisa",
    "James", "Mary", "William", "Patricia", "Richard", "Linda", "Joseph", "Barbara",
    "Thomas", "Elizabeth", "Charles", "Susan", "Daniel", "Jessica", "Matthew", "Karen",
    "Anthony", "Nancy", "Mark", "Betty", "Donald", "Margaret", "Steven", "Sandra",
    "Paul", "Ashley", "Andrew", "Kimberly", "Joshua", "Emily", "Kenneth", "Donna",
    "Kevin", "Michelle", "Brian", "Carol", "George", "Amanda", "Timothy", "Melissa",
    "Ronald", "Deborah", "Jason", "Stephanie", "Edward", "Rebecca", "Jeffrey", "Sharon",
    "Ryan", "Laura", "Jacob", "Cynthia", "Gary", "Kathleen", "Nicholas", "Amy",
    "Eric", "Angela", "Jonathan", "Shirley", "Stephen", "Anna", "Larry", "Brenda",
    "Justin", "Pamela", "Scott", "Emma", "Brandon", "Nicole", "Benjamin", "Helen",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy",
    "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey",
    "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson",
]

# Real US cities with county + state + typical price ranges
CITIES = [
    # (City, County, State, Min Price, Max Price)
    ("Phoenix", "Maricopa", "AZ", 180000, 550000),
    ("Houston", "Harris", "TX", 150000, 480000),
    ("Dallas", "Dallas", "TX", 180000, 520000),
    ("Austin", "Travis", "TX", 250000, 750000),
    ("Plano", "Collin", "TX", 220000, 600000),
    ("Mesa", "Maricopa", "AZ", 170000, 450000),
    ("Tucson", "Pima", "AZ", 140000, 400000),
    ("Tampa", "Hillsborough", "FL", 200000, 550000),
    ("Orlando", "Orange", "FL", 190000, 480000),
    ("Miami", "Miami-Dade", "FL", 280000, 850000),
    ("Atlanta", "Fulton", "GA", 200000, 600000),
    ("Charlotte", "Mecklenburg", "NC", 220000, 550000),
    ("Raleigh", "Wake", "NC", 250000, 620000),
    ("Nashville", "Davidson", "TN", 220000, 580000),
    ("Memphis", "Shelby", "TN", 130000, 380000),
    ("Columbus", "Franklin", "OH", 150000, 420000),
    ("Cleveland", "Cuyahoga", "OH", 100000, 320000),
    ("Cincinnati", "Hamilton", "OH", 140000, 400000),
    ("Indianapolis", "Marion", "IN", 130000, 380000),
    ("Kansas City", "Jackson", "MO", 140000, 400000),
    ("St. Louis", "St. Louis", "MO", 120000, 380000),
    ("Detroit", "Wayne", "MI", 80000, 280000),
    ("Las Vegas", "Clark", "NV", 230000, 600000),
    ("Denver", "Denver", "CO", 280000, 750000),
    ("Colorado Springs", "El Paso", "CO", 220000, 520000),
]

# Real street names (common US street names)
STREET_NAMES = [
    "Oak", "Maple", "Pine", "Cedar", "Elm", "Washington", "Lake", "Hill",
    "Park", "Walnut", "Sunset", "Ridge", "Main", "Highland", "Forest",
    "River", "Meadow", "Valley", "Spring", "Cherry", "Willow", "Birch",
    "Chestnut", "Magnolia", "Bay", "Harbor", "Atlantic", "Pacific",
    "Lincoln", "Jefferson", "Madison", "Adams", "Jackson", "Franklin",
    "Cambridge", "Oxford", "Bristol", "Windsor", "Hampton", "Sheffield",
    "Cypress", "Lakeshore", "Hillside", "Meadowlark", "Sycamore", "Poplar",
    "Aspen", "Juniper", "Canyon", "Bluff", "Grove", "Orchard", "Vineyard",
]

STREET_TYPES = ["St", "Ave", "Rd", "Ln", "Dr", "Ct", "Way", "Blvd", "Pl", "Cir"]


def random_phone():
    """Generate realistic US phone number."""
    area_codes = ["214", "305", "404", "469", "480", "512", "602", "615",
                  "619", "702", "713", "786", "813", "901", "919", "972"]
    area = random.choice(area_codes)
    exchange = random.randint(200, 999)
    number = random.randint(1000, 9999)
    return f"({area}) {exchange}-{number}"


def random_street_address():
    """Generate realistic US street address."""
    number = random.randint(100, 9999)
    name = random.choice(STREET_NAMES)
    stype = random.choice(STREET_TYPES)
    return f"{number} {name} {stype}"


def generate_lead(idx, force_out_of_state=False):
    """Generate a single realistic lead."""
    city, county, state, min_p, max_p = random.choice(CITIES)
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)

    # Property address
    property_street = random_street_address()
    property_address = f"{property_street} {city} {state}"

    # Mailing address
    if force_out_of_state or random.random() < 0.30:  # 30% out-of-state
        # Different state
        other_cities = [c for c in CITIES if c[2] != state]
        mail_city, _, mail_state, _, _ = random.choice(other_cities)
        mail_street = random_street_address()
        mailing_address = f"{mail_street} {mail_city} {mail_state}"
    elif random.random() < 0.20:  # 20% in-state absentee (different city)
        same_state_cities = [c for c in CITIES if c[2] == state and c[0] != city]
        if same_state_cities:
            mail_city, _, _, _, _ = random.choice(same_state_cities)
            mail_street = random_street_address()
            mailing_address = f"{mail_street} {mail_city} {state}"
        else:
            mailing_address = property_address
    else:  # 50% owner occupied
        mailing_address = property_address

    # Listing type
    listing_type = random.choice(["FSBO", "price_drop", "FSBO", "price_drop", "FSBO"])

    # Prices
    list_price = random.randint(min_p, max_p)
    list_price = round(list_price / 1000) * 1000

    if listing_type == "price_drop":
        drop_pct = random.uniform(0.03, 0.22)  # 3-22% drop
        previous_price = int(list_price / (1 - drop_pct))
        previous_price = round(previous_price / 1000) * 1000
    else:
        previous_price = list_price

    # Owner name (some incomplete for realism)
    if random.random() < 0.03:  # 3% missing last name
        owner_name = first
    elif random.random() < 0.03:  # 3% missing owner entirely
        owner_name = ""
    else:
        owner_name = f"{first} {last}"

    # Phone (some missing)
    if random.random() < 0.10:  # 10% missing phone
        phone = ""
    else:
        phone = random_phone()

    return {
        "owner_name": owner_name,
        "address": property_address,
        "owner_mailing_address": mailing_address,
        "phone": phone,
        "listing_type": listing_type,
        "list_price": list_price,
        "previous_price": previous_price,
        "county": county,
    }


def main():
    print("Generating 100 realistic real estate leads...")

    random.seed(42)  # Reproducible data

    rows = []
    for i in range(100):
        rows.append(generate_lead(i))

    df = pd.DataFrame(rows)

    # Save to CSV
    output_path = Path("data/sample_100_leads.csv")
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"\n✅ Generated {len(df)} leads")
    print(f"📁 Saved to: {output_path}")
    print(f"\nBreakdown:")
    print(f"   FSBO: {len(df[df['listing_type'] == 'FSBO'])}")
    print(f"   Price Drop: {len(df[df['listing_type'] == 'price_drop'])}")
    print(f"   Missing owner: {df['owner_name'].isna().sum() + (df['owner_name'] == '').sum()}")
    print(f"   Missing phone: {(df['phone'] == '').sum()}")
    print(f"   Out-of-state (likely): ~30%")


if __name__ == "__main__":
    main()
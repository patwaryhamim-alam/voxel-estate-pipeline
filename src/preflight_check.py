import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

import warnings
warnings.filterwarnings("ignore")

import json
import sys
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
REQUIRED_COLUMNS = ["Address", "City", "State", "Price", "Beds", "Baths", 
                    "FSBO", "PriceDrop", "YearBuilt", "OwnerName"]

passed = []
failed = []


def check(name, condition, success_msg, fail_msg):
    """Helper: check pass/fail log koro"""
    if condition:
        passed.append(f"✅ {name}: {success_msg}")
    else:
        failed.append(f"❌ {name}: {fail_msg}")


# ============================================================
# Check 1: .env file ache?
# ============================================================
check(
    "Environment File",
    Path(".env").exists(),
    ".env file pawa geche",
    ".env file nei! API key chara cholbe na."
)

# ============================================================
# Check 2: API Key set ache?
# ============================================================
api_key = os.getenv("GEMINI_API_KEY")
check(
    "API Key",
    bool(api_key and len(api_key) > 20),
    f"Key set ache ({api_key[:10]}...)",
    "GEMINI_API_KEY set kora nei ba khub choto"
)

# ============================================================
# Check 3: CSV file ache?
# ============================================================
csv_path = Path("data/sample_leads.csv")
check(
    "CSV File",
    csv_path.exists(),
    "data/sample_leads.csv pawa geche",
    "data/sample_leads.csv pawa jay ni!"
)

# ============================================================
# Check 4: CSV format thik ache?
# ============================================================
if csv_path.exists():
    try:
        df = pd.read_csv(csv_path)
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        check(
            "CSV Columns",
            len(missing_cols) == 0,
            f"Shob {len(REQUIRED_COLUMNS)} column ache, {len(df)} rows",
            f"Missing columns: {missing_cols}"
        )
    except Exception as e:
        check("CSV Read", False, "", f"CSV porte parlam na: {e}")
else:
    check("CSV Columns", False, "", "CSV nei, tai check korte parlam na")

# ============================================================
# Check 5: AI connection kaj kore?
# ============================================================
if api_key and csv_path.exists():
    try:
        llm = ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            google_api_key=api_key
        )
        test_response = llm.invoke('Reply with ONLY this JSON: {"status": "ok"}')
        raw = test_response.text.strip()
        
        # Markdown fence thakle clean
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        parsed = json.loads(raw)
        check(
            "AI Connection",
            parsed.get("status") == "ok",
            f"Model '{MODEL_NAME}' kaj korche",
            f"AI JSON parse korte parlam na: {raw[:100]}"
        )
    except Exception as e:
        check("AI Connection", False, "", f"AI call fail: {e}")
else:
    check("AI Connection", False, "", "API key ba CSV nei, tai test korte parlam na")

# ============================================================
# FINAL REPORT
# ============================================================
print("\n" + "=" * 60)
print("  PREFLIGHT CHECK REPORT")
print("=" * 60 + "\n")

for line in passed:
    print(line)

if failed:
    print()
    for line in failed:
        print(line)

print("\n" + "=" * 60)

if failed:
    print(f"❌ RESULT: {len(failed)} issue(s) found. FIX KORO BEFORE RUN!")
    print("=" * 60)
    sys.exit(1)
else:
    print(f"✅ RESULT: All {len(passed)} checks passed. Ready to run!")
    print("=" * 60)
    sys.exit(0)
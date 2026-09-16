import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
import warnings
warnings.filterwarnings("ignore")

load_dotenv()

# .env theke model name load koro
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# Ekta single lead test korbo
test_lead = {
    "Address": "147 Walnut Way",
    "City": "Austin",
    "State": "TX",
    "Price": 95000,
    "Beds": 2,
    "Baths": 1,
    "FSBO": "Yes",
    "PriceDrop": "Yes",
    "YearBuilt": 1960,
    "OwnerName": "Robert Taylor"
}

# AI ke prompt banao
prompt = f"""
You are a real estate lead analyzer. Rate this seller's motivation 1-10.

Lead details:
- Address: {test_lead['Address']}, {test_lead['City']}, {test_lead['State']}
- Price: ${test_lead['Price']}
- Beds/Baths: {test_lead['Beds']}/{test_lead['Baths']}
- FSBO (For Sale By Owner): {test_lead['FSBO']}
- Price Drop: {test_lead['PriceDrop']}
- Year Built: {test_lead['YearBuilt']}

Give ONLY a JSON output like this, no extra text:
{{"score": 8, "reasons": ["reason 1", "reason 2"], "action": "Call within 24 hours"}}
"""

try:
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=os.getenv("GEMINI_API_KEY")
    )
    
    response = llm.invoke(prompt)
    
    print("=== LEAD ===")
    print(f"{test_lead['Address']}, {test_lead['City']}")
    print(f"Price: ${test_lead['Price']}")
    print()
    print("=== AI ANALYSIS ===")
    print(response.text)

except Exception as e:
    print(f"ERROR: {e}")
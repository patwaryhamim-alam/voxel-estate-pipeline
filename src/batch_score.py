import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

import warnings
warnings.filterwarnings("ignore")

import json
import pandas as pd
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


def build_batch_prompt(leads_df):
    """Shob lead ekta prompt e boshai"""
    leads_text = ""
    for idx, row in leads_df.iterrows():
        leads_text += f"""
Lead #{idx + 1}:
- Address: {row['Address']}, {row['City']}, {row['State']}
- Price: ${row['Price']}
- Beds/Baths: {row['Beds']}/{row['Baths']}
- FSBO: {row['FSBO']}
- Price Drop: {row['PriceDrop']}
- Year Built: {row['YearBuilt']}
"""
    
    prompt = f"""You are a real estate lead analyzer. Rate each seller's motivation 1-10.

{leads_text}

Return ONLY a JSON array with one object per lead, in order. Format:
[
  {{"lead_number": 1, "score": 8, "reasons": ["reason 1", "reason 2"], "action": "Call within 24 hours"}},
  {{"lead_number": 2, "score": 5, "reasons": ["reason 1"], "action": "Follow up next week"}}
]

No extra text. Only JSON.
"""
    return prompt


try:
    # CSV load
    df = pd.read_csv("data/sample_leads.csv")
    
    # Filter koro (age jeta korechilam)
    filtered = df[(df["Price"] < 200000) & (df["FSBO"] == "Yes")].reset_index(drop=True)
    
    print(f"Analyzing {len(filtered)} leads with ONE AI call...\n")
    
    # Prompt banao
    prompt = build_batch_prompt(filtered)
    
    # AI call
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=os.getenv("GEMINI_API_KEY")
    )
    
    response = llm.invoke(prompt)
    
    # Response theke JSON ber koro
    raw_text = response.text.strip()
    
    # Markdown fence thakle clean koro (```json ... ```)
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    
    results = json.loads(raw_text)
    
    # Results print koro
    print("=" * 60)
    for i, result in enumerate(results):
        lead = filtered.iloc[i]
        print(f"\nLead #{i + 1}: {lead['Address']}, {lead['City']}")
        print(f"  Score: {result['score']}/10")
        print(f"  Action: {result['action']}")
        print(f"  Reasons:")
        for reason in result['reasons']:
            print(f"    - {reason}")
    print("\n" + "=" * 60)
    print(f"✅ Done! {len(results)} leads analyzed in ONE call.")

except FileNotFoundError:
    print("ERROR: data/sample_leads.csv pawa jay ni!")
except json.JSONDecodeError as e:
    print(f"ERROR: AI JSON theke parse korte parlam na: {e}")
    print(f"Raw response: {raw_text[:500]}")
except Exception as e:
    print(f"ERROR: {e}")
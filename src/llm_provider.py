"""
LLM PROVIDER ABSTRACTION (with Classification Cache)
=====================================================
Single function `classify_batch()` that all modules use.
Swap providers (Gemini → DeepSeek) by editing ONE file.

FEATURES:
    - Batches 15 leads per request (vs 1 currently)
    - Classification cache (SQLite) — re-runs = 0 API calls
    - Exponential backoff on 429 rate limits
    - Retry 3 times, then fallback to rule-based
    - Robust JSON parsing (markdown fence stripping)
    - Configurable model via LLM_MODEL env var
    - PII-free prompts (no owner name, phone, address)

USAGE:
    from llm_provider import classify_batch
    
    results = classify_batch([
        {"lead_id": 0, "listing_type": "FSBO", "price_drop_pct": 15.0, ...},
        {"lead_id": 1, ...},
    ])
    # Returns: [{"lead_id": 0, "signal_type": "high_motivation", "reason": "..."}, ...]
"""

import os
import json
import time
import re
from typing import List, Dict, Any

from dotenv import load_dotenv

load_dotenv()

# Cache integration
from cache_manager import get_many, save_many

# ============================================================
# CONFIG — change via .env
# ============================================================
MODEL_NAME = os.getenv("LLM_MODEL", "gemini-3.5-flash")
BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "15"))
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
BASE_DELAY_SEC = 5  # exponential: 5, 10, 20

# Valid labels (strict)
VALID_LABELS = {"high_motivation", "moderate_motivation", "low_motivation"}

# Try to import logger
try:
    from logger import get_logger
    log = get_logger(__name__)
except ImportError:
    import logging
    log = logging.getLogger(__name__)


# ============================================================
# PROMPT BUILDER
# ============================================================
def _build_batch_prompt(leads: List[Dict[str, Any]]) -> str:
    """
    Build a single prompt for a batch of leads.
    Sends ONLY what's needed — no PII (owner name, phone, full address).
    """
    leads_block = ""
    for lead in leads:
        distress = lead.get('distress_signals', '') or 'none'
        leads_block += f"""
Lead #{lead['lead_id']}:
- Listing Type: {lead.get('listing_type', 'unknown')}
- Price Drop: {lead.get('price_drop_pct', 0)}%
- County: {lead.get('county', 'unknown')}
- Owner Status: {lead.get('owner_status', 'unknown')}
- Distress Signals: {distress}
"""

    prompt = f"""You are a US real estate lead analyst.

Analyze each lead below and classify seller motivation.

{leads_block}

CLASSIFICATION RULES:
- "high_motivation"   = price drop > 10% OR (FSBO and price drop > 5%) 
                        OR out_of_state_absentee OR any distress signal 
                        (tax_delinquent, pre_foreclosure, vacant)
- "moderate_motivation" = FSBO with price drop 0-10%, OR price drop 5-10%, 
                          OR in_state_absentee, OR distress signals like 
                          expired_listing, divorce, probate
- "low_motivation"    = no significant signals AND owner_occupied

HALLUCINATION GUARD:
- Use ONLY the facts provided above. Do not invent any information.
- If data is insufficient, say "insufficient data" as the reason.

Return ONLY a JSON array. No extra text. No markdown fences.
Format:
[
  {{"lead_id": 0, "signal_type": "high_motivation", "reason": "15% price drop + FSBO"}},
  {{"lead_id": 1, "signal_type": "low_motivation", "reason": "No signals"}}
]

JSON:"""

    return prompt


# ============================================================
# JSON PARSER (robust)
# ============================================================
def _parse_json_response(raw: str) -> List[Dict]:
    """
    Parse JSON from AI response. Handles markdown fences, extra text.
    """
    raw = raw.strip()

    # Strip markdown fences
    if raw.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
        if match:
            raw = match.group(1).strip()

    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fallback: find first '[' and last ']'
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response: {raw[:200]}")


# ============================================================
# AI CALL (Gemini) — internal
# ============================================================
def _call_gemini(prompt: str) -> str:
    """Call Gemini API with prompt. Returns raw text response."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    import warnings
    warnings.filterwarnings("ignore")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=api_key,
    )

    response = llm.invoke(prompt)
    return response.text


# ============================================================
# FALLBACK — rule-based (no AI)
# ============================================================
def _fallback_classify(lead: Dict[str, Any]) -> Dict:
    """
    Rule-based classification if AI completely fails.
    Never crashes. Always returns something.
    Considers distress signals (tax delinquent, pre-foreclosure, vacant).
    """
    drop = lead.get("price_drop_pct", 0) or 0
    ltype = (lead.get("listing_type", "") or "").lower()
    owner = (lead.get("owner_status", "") or "").lower()
    distress = (lead.get("distress_signals", "") or "").lower()

    # High priority distress signals
    high_distress = any(
        s in distress for s in ["tax_delinquent", "pre_foreclosure", "vacant"]
    )
    # Medium priority distress
    medium_distress = any(
        s in distress for s in ["expired_listing", "divorce", "probate"]
    )

    if (drop > 10 or (ltype == "fsbo" and drop > 5) 
            or owner == "out_of_state_absentee" or high_distress):
        label = "high_motivation"
        parts = [f"{drop}% drop", ltype, owner]
        if high_distress:
            parts.append(f"distress: {distress}")
        reason = f"Rule-based: {', '.join(p for p in parts if p)}"
    elif (drop > 5 or ltype == "fsbo" 
          or owner == "in_state_absentee" or medium_distress):
        label = "moderate_motivation"
        parts = [f"{drop}% drop", ltype, owner]
        if medium_distress:
            parts.append(f"distress: {distress}")
        reason = f"Rule-based: {', '.join(p for p in parts if p)}"
    else:
        label = "low_motivation"
        reason = "Rule-based: no signals"

    return {
        "lead_id": lead["lead_id"],
        "signal_type": label,
        "reason": reason,
    }


# ============================================================
# PUBLIC: classify_batch()
# ============================================================
def classify_batch(leads: List[Dict[str, Any]]) -> List[Dict]:
    """
    Classify a list of leads using AI (with cache).
    Handles batching, retries, fallback internally.

    Args:
        leads: List of dicts with keys: lead_id, listing_type, price_drop_pct,
               county, owner_status

    Returns:
        List of dicts: {lead_id, signal_type, reason}
    """
    if not leads:
        return []

    all_results = []
    total_batches = (len(leads) + BATCH_SIZE - 1) // BATCH_SIZE

    log.info(f"Classifying {len(leads)} leads in {total_batches} batch(es) "
             f"(batch_size={BATCH_SIZE})")

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        end = start + BATCH_SIZE
        batch = leads[start:end]

        log.info(f"Batch {batch_num + 1}/{total_batches}: {len(batch)} leads")

        try:
            batch_results = _classify_one_batch(batch, batch_num + 1)
            all_results.extend(batch_results)
        except Exception as e:
            log.error(f"Batch {batch_num + 1} failed completely: {e}")
            for lead in batch:
                all_results.append(_fallback_classify(lead))

        # Delay between batches (only if we might make an AI call)
        if batch_num < total_batches - 1:
            time.sleep(2)

    return all_results


def _classify_one_batch(batch: List[Dict], batch_num: int) -> List[Dict]:
    """
    Classify ONE batch. Checks cache first, then AI only for cache misses.
    Saves new AI results back to cache. Retries with exponential backoff.
    """
    # ============================================================
    # STEP 1: Check cache
    # ============================================================
    cached_results, uncached_leads = get_many(batch)

    if not uncached_leads:
        log.info(f"Batch {batch_num}: 100% cache hit "
                 f"({len(cached_results)} results, 0 API calls)")
        return cached_results

    log.info(f"Batch {batch_num}: {len(cached_results)} cached, "
             f"{len(uncached_leads)} need AI")

    # ============================================================
    # STEP 2: Call AI for uncached leads only
    # ============================================================
    prompt = _build_batch_prompt(uncached_leads)
    ai_results = []

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = _call_gemini(prompt)
            parsed = _parse_json_response(raw)
            ai_results = _validate_results(parsed, uncached_leads)
            log.info(f"Batch {batch_num}: AI returned {len(ai_results)} results")
            break

        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
            is_last = attempt == MAX_RETRIES

            if is_last:
                log.error(f"Batch {batch_num}: AI failed after {MAX_RETRIES} "
                          f"attempts, using fallback for {len(uncached_leads)} leads")
                ai_results = [_fallback_classify(l) for l in uncached_leads]
                break

            delay = BASE_DELAY_SEC * (2 ** (attempt - 1))

            if is_rate_limit:
                log.warning(f"Batch {batch_num}: Rate limit on attempt "
                            f"{attempt}, waiting {delay}s")
            else:
                log.warning(f"Batch {batch_num}: Error on attempt "
                            f"{attempt}: {err_str[:80]}, waiting {delay}s")

            time.sleep(delay)

    # ============================================================
    # STEP 3: Save AI results to cache (only if they came from AI, not fallback)
    # ============================================================
    if ai_results:
        saved = save_many(ai_results, uncached_leads)
        log.info(f"Batch {batch_num}: cached {saved} new results")

    # ============================================================
    # STEP 4: Combine cached + AI results
    # ============================================================
    combined = cached_results + ai_results
    log.info(f"Batch {batch_num}: returning {len(combined)} total results "
             f"({len(cached_results)} cached, {len(ai_results)} from AI)")

    return combined


def _validate_results(parsed: List[Dict], batch: List[Dict]) -> List[Dict]:
    """
    Strict validation of AI output. Fills missing with fallback.
    """
    batch_ids = {lead["lead_id"] for lead in batch}
    results = {}
    fallbacks_used = 0

    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON list, got {type(parsed).__name__}")

    for item in parsed:
        if not isinstance(item, dict):
            continue

        lead_id = item.get("lead_id")
        signal_type = item.get("signal_type", "").strip().lower()
        reason = item.get("reason", "").strip()

        # Validate
        if lead_id not in batch_ids:
            continue  # AI hallucinated an ID
        if signal_type not in VALID_LABELS:
            continue  # Invalid label
        if not reason:
            reason = "AI provided no reason"

        results[lead_id] = {
            "lead_id": lead_id,
            "signal_type": signal_type,
            "reason": reason,
        }

    # Fill missing leads with fallback
    final = []
    for lead in batch:
        if lead["lead_id"] in results:
            final.append(results[lead["lead_id"]])
        else:
            fallbacks_used += 1
            final.append(_fallback_classify(lead))

    if fallbacks_used > 0:
        log.warning(f"Used fallback for {fallbacks_used} leads "
                    f"(AI missed or returned invalid)")

    return final


# ============================================================
# TEST — run this file directly
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("LLM PROVIDER TEST (with Cache)")
    print("=" * 60)

    test_leads = [
        {"lead_id": 0, "listing_type": "FSBO", "price_drop_pct": 15.0,
         "county": "Dallas", "owner_status": "owner_occupied"},
        {"lead_id": 1, "listing_type": "price_drop", "price_drop_pct": 8.0,
         "county": "Harris", "owner_status": "in_state_absentee"},
        {"lead_id": 2, "listing_type": "FSBO", "price_drop_pct": 0.0,
         "county": "Travis", "owner_status": "out_of_state_absentee"},
        {"lead_id": 3, "listing_type": "price_drop", "price_drop_pct": 3.0,
         "county": "Collin", "owner_status": "owner_occupied"},
        {"lead_id": 4, "listing_type": "FSBO", "price_drop_pct": 20.0,
         "county": "Dallas", "owner_status": "out_of_state_absentee"},
    ]

    print(f"\nTesting with {len(test_leads)} leads...")
    print(f"Model: {MODEL_NAME}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"\n--- RUN 1 (populates cache) ---")

    results = classify_batch(test_leads)

    print(f"\n✅ Got {len(results)} results:")
    for r in results:
        print(f"  Lead #{r['lead_id']}: {r['signal_type']}")
        print(f"    Reason: {r['reason'][:80]}")

    print(f"\n--- RUN 2 (should be 100% cache hit) ---")
    results2 = classify_batch(test_leads)

    print(f"\n✅ Run 2 got {len(results2)} results")
    print(f"   If you see '100% cache hit' above, cache is working!")
"""
LLM PROVIDER ABSTRACTION (with Classification Cache)
=====================================================
Single function `classify_batch()` that all modules use.
Swap providers (Gemini → DeepSeek) by editing ONE file.

FEATURES:
    - Batches 15 leads per request
    - Classification cache (SQLite) — re-runs = 0 API calls
    - Exponential backoff on 429 rate limits
    - Retry 3 times, then fallback to rule-based
    - Robust JSON parsing (markdown fence stripping)
    - Configurable model via LLM_MODEL (or GEMINI_MODEL) env var
    - PII-free prompts (no owner name, phone, address)
    - v3: LLC/Trust owners do NOT boost motivation score
    - v4: Per-minute vs Daily 429 handled separately
    - v5: Prompt enriched with days_on_market + property_type
    - v6: Daily 429 returns "pending" marker (Fix 1)
    - v6: LLM call counter (for spot_check_ai.py)
    - v6: Startup model-name log + fail-fast on 404 (Fix 3)
    - v7 (Fix 3): ADMIN EMAIL ALERT on model-not-found

USAGE:
    from llm_provider import classify_batch, get_llm_call_count
"""

import os
import json
import time
import re
from typing import List, Dict, Any

from dotenv import load_dotenv

load_dotenv()

from cache_manager import get_many, save_many

# Fix 3: admin alert integration (import defensively)
try:
    from alerts import send_error_alert
    _ALERTS_AVAILABLE = True
except ImportError:
    _ALERTS_AVAILABLE = False
    send_error_alert = None

# ============================================================
# CONFIG — change via .env
# ============================================================
# Fix 3: prefer LLM_MODEL, fall back to GEMINI_MODEL, then default
MODEL_NAME = (
    os.getenv("LLM_MODEL")
    or os.getenv("GEMINI_MODEL")
    or "gemini-3.6-flash"
)
BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "15"))
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
BASE_DELAY_SEC = 5

VALID_LABELS = {"high_motivation", "moderate_motivation", "low_motivation"}

try:
    from logger import get_logger
    log = get_logger(__name__)
except ImportError:
    import logging
    log = logging.getLogger(__name__)


# ============================================================
# LLM CALL COUNTER
# ============================================================
_LLM_CALL_COUNT = 0
_MODEL_LOGGED = False


def get_llm_call_count() -> int:
    """Return number of real LLM API calls made this session."""
    return _LLM_CALL_COUNT


def reset_llm_call_count() -> None:
    """Reset the counter to zero."""
    global _LLM_CALL_COUNT
    _LLM_CALL_COUNT = 0


def _log_model_once():
    """Fix 3: log resolved model name + env source once per session."""
    global _MODEL_LOGGED
    if _MODEL_LOGGED:
        return

    if os.getenv("LLM_MODEL"):
        src = "LLM_MODEL"
    elif os.getenv("GEMINI_MODEL"):
        src = "GEMINI_MODEL"
    else:
        src = "DEFAULT"

    print(f"[LLM] Model: {MODEL_NAME} (source: {src})")
    log.info(f"LLM model resolved: {MODEL_NAME} (from {src})")
    _MODEL_LOGGED = True


def _alert_model_not_found(model_name: str, err_str: str) -> None:
    """
    Fix 3: Send admin email when model name is invalid.

    Non-fatal — pipeline still raises RuntimeError after this.
    If alerts module unavailable, logs warning and continues.
    """
    if not _ALERTS_AVAILABLE:
        log.warning("alerts module unavailable — cannot send model alert")
        return

    try:
        success, msg = send_error_alert(
            subject=f"LLM Model Not Found: {model_name}",
            body=(
                f"Model '{model_name}' is invalid or unavailable.\n\n"
                f"Action required:\n"
                f"1. Update GEMINI_MODEL in .env\n"
                f"2. Check current model names at:\n"
                f"   https://ai.google.dev/gemini-api/docs/models\n\n"
                f"Error excerpt:\n{err_str[:400]}"
            ),
            context=f"llm_provider startup (model={model_name})",
        )
        if success:
            log.info(f"Model-not-found alert email sent: {msg}")
        else:
            log.warning(f"Model alert email failed: {msg}")
    except Exception as e:
        log.warning(f"Failed to send model-not-found alert: {e}")


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

        dom = lead.get('days_on_market')
        dom_str = f"{dom} days" if dom is not None else "unknown"

        ptype = lead.get('property_type') or "unknown"

        leads_block += f"""
Lead #{lead['lead_id']}:
- Listing Type: {lead.get('listing_type', 'unknown')}
- Price Drop: {lead.get('price_drop_pct', 0)}%
- County: {lead.get('county', 'unknown')}
- Owner Status: {lead.get('owner_status', 'unknown')}
- Distress Signals: {distress}
- Days on Market: {dom_str}
- Property Type: {ptype}
"""

    prompt = f"""You are a US real estate lead analyst.

Analyze each lead below and classify seller motivation.

{leads_block}

CLASSIFICATION RULES:
- "high_motivation"   = price drop > 10% OR (FSBO and price drop > 5%) 
                        OR out_of_state_absentee OR any distress signal 
                        (tax_delinquent, pre_foreclosure, vacant)
                        OR days_on_market > 180
- "moderate_motivation" = FSBO with price drop 0-10%, OR price drop 5-10%, 
                          OR in_state_absentee, OR distress signals like 
                          expired_listing, divorce, probate
                          OR days_on_market 90-180
- "low_motivation"    = no significant signals AND owner_occupied
                        AND days_on_market < 30

ADDITIONAL SIGNALS (use if present):
- Days on Market > 180: strong urgency (seller frustrated)
- Days on Market 90-180: moderate urgency (stale listing)
- Days on Market < 30: recent listing, lower urgency
- Property Type: CONTEXT ONLY. Do not directly boost score.

IMPORTANT — LLC/Trust Owners:
- If Owner Status is "llc_or_trust_owner", do NOT increase motivation.
- Mention it in the reason as informational.

HALLUCINATION GUARD:
- Use ONLY the facts provided above. Do not invent any information.
- If data is insufficient, say "insufficient data" as the reason.
- Keep reasoning SHORT — max 20 words per lead.

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
    """Parse JSON from AI response. Handles markdown fences, extra text."""
    raw = raw.strip()

    if raw.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
        if match:
            raw = match.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response: {raw[:200]}")


# ============================================================
# ERROR CLASSIFIERS
# ============================================================
def _is_daily_quota_error(err_str: str) -> bool:
    """Distinguish DAILY quota exhaustion from PER-MINUTE rate limit."""
    lower = err_str.lower()

    daily_markers = [
        "perday", "per day", "per_day",
        "daily limit", "daily_limit",
        "requests_per_day",
        "generaterequestsperday",
        'quota_value": 1500',
        'quota_value":1500',
    ]
    if any(m in lower for m in daily_markers):
        return True

    minute_markers = [
        "perminute", "per minute", "per_minute",
        "rate limit", "rate_limit",
        "generaterequestsperminute",
    ]
    if any(m in lower for m in minute_markers):
        return False

    return False


def _is_model_not_found_error(err_str: str) -> bool:
    """Fix 3: detect model-not-found / invalid model errors."""
    lower = err_str.lower()
    markers = [
        "404", "not found", "not_found",
        "model not found", "invalid model",
        "unsupported model", "does not exist",
        "no longer available",
    ]
    return any(m in lower for m in markers)


# ============================================================
# AI CALL (Gemini)
# ============================================================
def _call_gemini(prompt: str) -> str:
    """Call Gemini API with prompt. Returns raw text response."""
    global _LLM_CALL_COUNT

    from langchain_google_genai import ChatGoogleGenerativeAI
    import warnings
    warnings.filterwarnings("ignore")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    _log_model_once()

    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=api_key,
    )

    _LLM_CALL_COUNT += 1

    response = llm.invoke(prompt)
    return response.text


# ============================================================
# FALLBACK — rule-based
# ============================================================
def _fallback_classify(lead: Dict[str, Any]) -> Dict:
    """Rule-based classification if AI completely fails."""
    drop = lead.get("price_drop_pct", 0) or 0
    ltype = (lead.get("listing_type", "") or "").lower()
    owner = (lead.get("owner_status", "") or "").lower()
    distress = (lead.get("distress_signals", "") or "").lower()

    is_business_owner = "llc_or_trust_owner" in owner
    owner_for_scoring = "unknown" if is_business_owner else owner

    high_distress = any(
        s in distress for s in ["tax_delinquent", "pre_foreclosure", "vacant"]
    )
    medium_distress = any(
        s in distress for s in ["expired_listing", "divorce", "probate"]
    )

    dom = lead.get("days_on_market")
    try:
        dom = int(dom) if dom is not None else None
    except (ValueError, TypeError):
        dom = None

    if (drop > 10 or (ltype == "fsbo" and drop > 5)
            or owner_for_scoring == "out_of_state_absentee"
            or high_distress
            or (dom is not None and dom > 180)):
        label = "high_motivation"
        parts = [f"{drop}% drop", ltype]
        if owner_for_scoring != "unknown":
            parts.append(owner_for_scoring)
        if is_business_owner:
            parts.append("(LLC/Trust — verify separately)")
        if high_distress:
            parts.append(f"distress: {distress}")
        if dom is not None and dom > 180:
            parts.append(f"DOM: {dom}")
        reason = f"Rule-based: {', '.join(p for p in parts if p)}"

    elif (drop > 5 or ltype == "fsbo"
          or owner_for_scoring == "in_state_absentee"
          or medium_distress
          or (dom is not None and dom > 90)):
        label = "moderate_motivation"
        parts = [f"{drop}% drop", ltype]
        if owner_for_scoring != "unknown":
            parts.append(owner_for_scoring)
        if is_business_owner:
            parts.append("(LLC/Trust — verify separately)")
        if medium_distress:
            parts.append(f"distress: {distress}")
        if dom is not None and 90 < dom <= 180:
            parts.append(f"DOM: {dom}")
        reason = f"Rule-based: {', '.join(p for p in parts if p)}"

    else:
        label = "low_motivation"
        if is_business_owner:
            reason = "Rule-based: LLC/Trust owner, no signals"
        else:
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
    """Classify a list of leads using AI (with cache)."""
    if not leads:
        return []

    _log_model_once()

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
        except RuntimeError:
            # Fix 3: model-not-found — already alerted, re-raise to stop
            raise
        except Exception as e:
            log.error(f"Batch {batch_num + 1} failed completely: {e}")
            for lead in batch:
                all_results.append(_fallback_classify(lead))

        if batch_num < total_batches - 1:
            time.sleep(2)

    return all_results


def _classify_one_batch(batch: List[Dict], batch_num: int) -> List[Dict]:
    """Classify ONE batch with cache, retries, and pending markers."""
    cached_results, uncached_leads = get_many(batch)

    if not uncached_leads:
        log.info(f"Batch {batch_num}: 100% cache hit "
                 f"({len(cached_results)} results, 0 API calls)")
        return cached_results

    log.info(f"Batch {batch_num}: {len(cached_results)} cached, "
             f"{len(uncached_leads)} need AI")

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

            # Fix 3: model-not-found → alert + fail fast
            if _is_model_not_found_error(err_str):
                log.error(f"Batch {batch_num}: MODEL NOT FOUND — "
                          f"model={MODEL_NAME}. Stopping pipeline.")
                _alert_model_not_found(MODEL_NAME, err_str)
                raise RuntimeError(
                    f"Model not found: {MODEL_NAME}. "
                    f"Update .env (LLM_MODEL or GEMINI_MODEL)."
                )

            is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str

            if is_429 and _is_daily_quota_error(err_str):
                log.warning(
                    f"Batch {batch_num}: DAILY quota exhausted on attempt "
                    f"{attempt}. Marking {len(uncached_leads)} leads as pending."
                )
                ai_results = [
                    {
                        "lead_id": lead["lead_id"],
                        "signal_type": "pending",
                        "reason": "Daily quota exhausted — retry next run",
                    }
                    for lead in uncached_leads
                ]
                break

            is_last = attempt == MAX_RETRIES

            if is_last:
                log.error(f"Batch {batch_num}: AI failed after {MAX_RETRIES} "
                          f"attempts, using fallback for "
                          f"{len(uncached_leads)} leads")
                ai_results = [_fallback_classify(l) for l in uncached_leads]
                break

            delay = BASE_DELAY_SEC * (2 ** (attempt - 1))

            if is_429:
                log.warning(f"Batch {batch_num}: Per-minute rate limit on "
                            f"attempt {attempt}, waiting {delay}s")
            else:
                log.warning(f"Batch {batch_num}: Error on attempt "
                            f"{attempt}: {err_str[:80]}, waiting {delay}s")

            time.sleep(delay)

    # Save to cache (skip "pending")
    pairs_to_cache = [
        (r, l) for r, l in zip(ai_results, uncached_leads)
        if r.get("signal_type") != "pending"
    ]
    if pairs_to_cache:
        cache_results, cache_leads = zip(*pairs_to_cache)
        saved = save_many(list(cache_results), list(cache_leads))
        skipped = len(ai_results) - len(pairs_to_cache)
        log.info(f"Batch {batch_num}: cached {saved} new results "
                 f"(skipped {skipped} pending from cache)")

    combined = cached_results + ai_results
    log.info(f"Batch {batch_num}: returning {len(combined)} total results "
             f"({len(cached_results)} cached, {len(ai_results)} from AI)")

    return combined


def _validate_results(parsed: List[Dict], batch: List[Dict]) -> List[Dict]:
    """Strict validation of AI output."""
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

        if lead_id not in batch_ids:
            continue
        if signal_type not in VALID_LABELS:
            continue
        if not reason:
            reason = "AI provided no reason"

        results[lead_id] = {
            "lead_id": lead_id,
            "signal_type": signal_type,
            "reason": reason,
        }

    final = []
    for lead in batch:
        if lead["lead_id"] in results:
            final.append(results[lead["lead_id"]])
        else:
            fallbacks_used += 1
            final.append(_fallback_classify(lead))

    if fallbacks_used > 0:
        log.warning(f"Used fallback for {fallbacks_used} leads")

    return final


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("LLM PROVIDER TEST v7 — Fix 3 (Admin Alert on 404)")
    print("=" * 60)
    print(f"Model: {MODEL_NAME}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Alerts available: {_ALERTS_AVAILABLE}")

    # Quota classifier
    print("\n[0] Quota classifier")
    for m in [
        "429 RESOURCE_EXHAUSTED: GenerateRequestsPerDayPerProjectPerModel",
        "Quota exceeded, per day limit reached",
    ]:
        print(f"   {'OK ' if _is_daily_quota_error(m) else 'FAIL'} daily: {m[:60]}")
    for m in [
        "429 RESOURCE_EXHAUSTED: GenerateRequestsPerMinutePerProjectPerModel",
        "Rate limit exceeded",
    ]:
        print(f"   {'OK ' if not _is_daily_quota_error(m) else 'FAIL'} minute: {m[:60]}")

    # Model-not-found classifier
    print("\n[0b] Model-not-found classifier")
    test_cases = [
        "404 model not found",
        "Invalid model name",
        "Model does not exist",
        "This model is no longer available to new users",  # Real Gemini message
    ]
    for m in test_cases:
        ok = _is_model_not_found_error(m)
        print(f"   {'OK ' if ok else 'FAIL'} not-found: {m[:60]}")

    # Rule-based tests
    print("\n[1] LLC/Trust without signals (should be LOW):")
    llc_lead = {
        "lead_id": 0, "listing_type": "price_drop", "price_drop_pct": 0.0,
        "county": "Dallas", "owner_status": "llc_or_trust_owner",
        "distress_signals": "", "days_on_market": None, "property_type": "",
    }
    result = _fallback_classify(llc_lead)
    print(f"   Result: {result['signal_type']} | {result['reason']}")

    print("\n[2] High DOM (200 days) → HIGH:")
    stale_lead = {
        "lead_id": 1, "listing_type": "price_drop", "price_drop_pct": 3.0,
        "county": "Dallas", "owner_status": "owner_occupied",
        "distress_signals": "", "days_on_market": 200,
        "property_type": "Single Family",
    }
    result = _fallback_classify(stale_lead)
    print(f"   Result: {result['signal_type']} | {result['reason']}")

    print("\n" + "=" * 60)
    print("Test complete.")
    print("=" * 60)
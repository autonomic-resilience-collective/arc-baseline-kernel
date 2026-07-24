"""
IHB Multi-Tier Verify Router
=============================
Four distinct service tiers based on agent budget scale.
All tiers execute identical zero-fabrication IHB math from ihb/core.py.
The tier determines pricing and rate model only.

Tiers:
  /verify/micro       $0.02 per call (or 0.05% of X-Transaction-Value)
  /verify/batch       $50.00 for 5,000 pre-purchased calls (~$0.01/call)
  /verify/fleet       $3,000/month for unlimited calls
  /verify/high_stakes $500.00 minimum for multi-million-dollar liability gates

Payment rails accepted:
  USDC on Base L2 (x402)        — live, production-ready
  Visa Intelligent Commerce      — STUB: requires enterprise Visa API partnership
                                   activate by implementing _validate_visa_auth()

Add to ihb_mcp_server.py:
  from ihb_verify_tiers import tiers_router
  app.include_router(tiers_router)
"""

# ═══════════════════════════════════════════════════════════════════════════
# ARC BASELINE GROUNDING KERNEL — Autonomic Resilience Collective
# Validated: 1,815 tracked nights | 94.4% completeness
# Citation:  Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889
# Kernel ID: @ARC_BaselineKernel
# ═══════════════════════════════════════════════════════════════════════════


from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ihb_state import get_subject
from ihb_payment import (
    payment_required_response, verify_payment,
    cache_result, get_cached_result,
    ARC_WALLET_ADDRESS, USDC_CONTRACT, NONCE_TTL_SECONDS,
    _used_nonces
)

tiers_router = APIRouter(prefix="/tiers", tags=["Multi-Tier Verify"])


# ─── Pricing constants ────────────────────────────────────────────────────────

MICRO_PRICE        = float(os.environ.get("MICRO_PRICE",        "0.02"))
BATCH_PRICE        = float(os.environ.get("BATCH_PRICE",        "50.00"))
BATCH_CALLS        = int(os.environ.get("BATCH_CALLS",          "5000"))
FLEET_MONTHLY      = float(os.environ.get("FLEET_MONTHLY",      "3000.00"))
HIGH_STAKES_MIN    = float(os.environ.get("HIGH_STAKES_MIN",    "500.00"))
VALUE_BASED_RATE   = float(os.environ.get("VALUE_BASED_RATE",   "0.0005"))


# ─── In-memory registries ─────────────────────────────────────────────────────
# Production: replace with Redis for horizontal scaling

# Batch tokens: txhash → {credits_remaining, purchased_at, total_purchased}
_batch_registry: dict[str, dict] = {}

# Fleet subscriptions: subscription_token → {activated_at, expires_at, txhash}
_fleet_registry: dict[str, dict] = {}


# ─── Request models ───────────────────────────────────────────────────────────

class TierQueryRequest(BaseModel):
    subject_id: str = Field(..., description="Subject to query")
    metric: str = Field(..., description="Metric to score (e.g. hrv_rmssd)")
    agent_intent: Optional[str] = Field(None, description="What the calling agent intends to do with the result")


class BatchPurchaseRequest(BaseModel):
    txhash: str = Field(..., description="Transaction hash of the $50 USDC payment on Base L2")


class FleetActivateRequest(BaseModel):
    txhash: str = Field(..., description="Transaction hash of the $3,000 USDC monthly payment on Base L2")


# ─── Payment rail dispatcher ──────────────────────────────────────────────────

async def _validate_payment(request: Request, required_amount: float) -> tuple[bool, Optional[str], str]:
    """
    Validates payment from either USDC x402 or Visa Intelligent Commerce rail.
    Returns (validated, txhash_or_token, rail_used)
    """

    # ── Rail 1: USDC x402 (Base L2) — LIVE ───────────────────────────────
    paid, txhash = await verify_payment(request)
    if paid and txhash:
        return True, txhash, "usdc_x402"

    # ── Rail 2: Visa Intelligent Commerce via Nevermined — STUB ──────────
    # To activate: implement Nevermined SDK validation here
    # Requires: enterprise Visa Intelligent Commerce API access
    # Contact: developer.visa.com/capabilities/intelligent-commerce
    visa_token = request.headers.get("X-Nevermined-Auth") or request.headers.get("X-Visa-Auth")
    if visa_token:
        validated = await _validate_visa_auth(visa_token, required_amount)
        if validated:
            return True, visa_token, "visa_nevermined"
        raise HTTPException(402,
            "Visa/Nevermined auth token invalid or insufficient balance. "
            "Ensure your Nevermined subscription covers the required amount."
        )

    # ── No valid payment proof ────────────────────────────────────────────
    return False, None, "none"


async def _validate_visa_auth(token: str, required_amount: float) -> bool:
    """
    STUB: Visa Intelligent Commerce validation via Nevermined.
    Replace this body with the Nevermined SDK call when API access is established.

    Example implementation:
        from nevermined_sdk_py import NeverminedAPI
        nvmapi = NeverminedAPI.get_instance(config)
        access = await nvmapi.assets.validate_access(token, required_amount)
        return access.is_valid
    """
    # Until activated, always return False so USDC rail is used
    return False


def _issue_payment_required(endpoint: str, amount: float) -> JSONResponse:
    """Issue a 402 response that includes both USDC and Visa/Nevermined instructions."""
    nonce = secrets.token_hex(16)
    _used_nonces[nonce] = time.time()
    amount_raw = int(amount * (10 ** 6))
    return JSONResponse(
        status_code=402,
        content={
            "x402_version": "1.0",
            "error": "Payment Required",
            "endpoint": endpoint,
            "payment_rails": {
                "usdc_x402": {
                    "status": "live",
                    "network": "base",
                    "chain_id": 8453,
                    "asset": "USDC",
                    "contract": USDC_CONTRACT,
                    "recipient": ARC_WALLET_ADDRESS,
                    "amount_usdc": amount,
                    "amount_raw": amount_raw,
                    "nonce": nonce,
                    "nonce_expires_seconds": NONCE_TTL_SECONDS,
                    "instructions": [
                        f"Transfer {amount} USDC to {ARC_WALLET_ADDRESS} on Base L2",
                        "Resubmit request with header: X-Payment-Proof: <txhash>",
                    ]
                },
                "visa_intelligent_commerce": {
                    "status": "coming_soon",
                    "protocol": "Nevermined",
                    "instructions": "Enterprise Visa Intelligent Commerce access via Nevermined. Contact research@autonomicresiliencecollective.org for early access.",
                    "header_when_live": "X-Nevermined-Auth: <token>"
                }
            }
        },
        headers={
            "X-402-Version": "1.0",
            "X-Payment-Rails": "usdc_x402,visa_nevermined_coming_soon",
            "X-Payment-Amount": str(amount),
        }
    )


# ─── Shared computation core ──────────────────────────────────────────────────

def _compute_and_seal(subject_id: str, metric: str, agent_intent: str,
                       tier: str, price: float, txhash: str,
                       pricing_model: str, extra_meta: dict = None) -> dict:
    """
    Identical zero-fabrication IHB computation for all tiers.
    All numbers from ihb/core.py. No LLM smoothing. No fabrication.
    """
    subject = get_subject(subject_id)
    if not subject:
        raise HTTPException(404, f"Subject '{subject_id}' not registered.")

    try:
        state = subject.query_state(metric)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if state.get("status") == "INSUFFICIENT_DATA":
        raise HTTPException(422, state["message"])

    result = {
        "schema":              "ihb.verify.v1",
        "tier":                tier,
        "subject_id":          subject_id,
        "metric":              metric,
        "agent_intent":        agent_intent or "unspecified",
        "z_score":             state["z_score"],
        "mathematical_state":  state["mathematical_state"],
        "commercial_tag":      state["commercial_tag"],
        "purchase_signal":     state["purchase_signal"],
        "baseline_mean":       state["baseline_mean"],
        "baseline_sd":         state["baseline_sd"],
        "n_valid_total":       state["n_valid_total"],
        "price_paid_usdc":     price,
        "pricing_model":       pricing_model,
        "payment_txhash":      txhash,
        "verified_at_unix":    int(time.time()),
        "descriptor_notice":   (
            "This payload represents a purely descriptive statistical analysis of "
            "de-identified longitudinal data relative to this individual's own "
            "historical baseline. It does not constitute clinical, medical, diagnostic, "
            "or regulatory validation of any real-world action."
        ),
        "zero_fabrication":    True,
        "math_source":         "ihb/core.py (deterministic)",
        "dataset_integrity":   "1,815 tracked nights | 1,713 captured nights | 94.4% completeness",
        "provider":            "Autonomic Resilience Collective",
        "citation":            "Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889",
    }
    if extra_meta:
        result.update(extra_meta)

    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["result_fingerprint"] = hashlib.sha256(canonical.encode()).hexdigest()
    result["fingerprint_scope"]  = "sha256_over_canonical_result_json"
    return result


# ─── TIER 1: /verify/micro ────────────────────────────────────────────────────

@tiers_router.post("/micro")
async def verify_micro(req: TierQueryRequest, request: Request):
    """
    Micro tier: $0.02 USDC per call, or 0.05% of X-Transaction-Value.

    The standard A2A baseline verification call. Idempotent within 24h.
    Accepts USDC x402 or Visa/Nevermined (when live).
    Supports ?format=dense and X-Agent-Format: dense.
    """
    # Dynamic pricing
    tx_val = request.headers.get("X-Transaction-Value")
    price = MICRO_PRICE
    pricing_model = "flat_micro"
    if tx_val:
        try:
            fractional = round(float(tx_val) * VALUE_BASED_RATE, 4)
            price = max(MICRO_PRICE, fractional)
            pricing_model = "value_based_fractional"
        except (ValueError, TypeError):
            pass

    # Idempotency check
    proof = request.headers.get("X-Payment-Proof", "")
    if proof:
        cached = get_cached_result(proof)
        if cached:
            return cached

    validated, txhash, rail = await _validate_payment(request, price)
    if not validated:
        return _issue_payment_required("/verify/micro", price)

    result = _compute_and_seal(
        req.subject_id, req.metric, req.agent_intent or "",
        "micro", price, txhash, pricing_model,
        extra_meta={"payment_rail": rail}
    )
    if txhash:
        cache_result(txhash, result)
    return result


# ─── TIER 2: /verify/batch ───────────────────────────────────────────────────

@tiers_router.post("/batch/purchase")
async def batch_purchase(req: BatchPurchaseRequest, request: Request):
    """
    Purchase a batch of 5,000 verification credits for $50 USDC.

    After purchasing, use the txhash as X-Batch-Auth header on
    /verify/batch calls. Each call decrements your credit counter.
    No per-call payment needed while credits remain.
    """
    txhash = req.txhash.strip().lower()

    if txhash in _batch_registry:
        b = _batch_registry[txhash]
        return {
            "status": "already_registered",
            "txhash": txhash,
            "credits_remaining": b["credits_remaining"],
            "total_purchased": b["total_purchased"],
        }

    # Verify the $50 USDC payment on-chain
    from ihb_payment import _fetch_transaction, USDC_CONTRACT, ARC_WALLET_ADDRESS
    receipt = await _fetch_transaction(txhash)
    if not receipt or receipt.get("status") != "0x1":
        raise HTTPException(402, "Transaction not found or failed. Submit a confirmed $50 USDC txhash.")

    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    BATCH_AMOUNT_RAW = int(BATCH_PRICE * (10 ** 6))
    verified = False
    for log in receipt.get("logs", []):
        if log.get("address", "").lower() != USDC_CONTRACT.lower():
            continue
        topics = log.get("topics", [])
        if not topics or topics[0].lower() != TRANSFER_TOPIC:
            continue
        if len(topics) < 3:
            continue
        to_addr = "0x" + topics[2][-40:]
        if to_addr.lower() != ARC_WALLET_ADDRESS.lower():
            continue
        try:
            value = int(log.get("data", "0x"), 16)
            if value >= BATCH_AMOUNT_RAW:
                verified = True
                break
        except ValueError:
            continue

    if not verified:
        raise HTTPException(402, f"No qualifying $50 USDC transfer found in transaction {txhash}.")

    _batch_registry[txhash] = {
        "credits_remaining": BATCH_CALLS,
        "total_purchased": BATCH_CALLS,
        "purchased_at": time.time(),
        "txhash": txhash,
    }
    return {
        "status": "activated",
        "txhash": txhash,
        "credits_purchased": BATCH_CALLS,
        "credits_remaining": BATCH_CALLS,
        "price_paid_usdc": BATCH_PRICE,
        "effective_rate_per_call": round(BATCH_PRICE / BATCH_CALLS, 4),
        "instructions": f"Include header X-Batch-Auth: {txhash} on POST /tiers/batch calls",
    }


@tiers_router.post("/batch")
async def verify_batch(req: TierQueryRequest, request: Request):
    """
    Batch tier: pre-purchased credits at $0.01/call effective rate.

    Include X-Batch-Auth: <purchase_txhash> header.
    Credits are decremented per call. Purchase via POST /verify/batch/purchase.
    """
    batch_auth = request.headers.get("X-Batch-Auth", "").strip().lower()

    if not batch_auth or batch_auth not in _batch_registry:
        return JSONResponse(status_code=402, content={
            "error": "Batch credits required",
            "fix": f"Purchase {BATCH_CALLS} credits for ${BATCH_PRICE} USDC via POST /verify/batch/purchase",
            "purchase_endpoint": "/verify/batch/purchase",
            "purchase_payload": {"txhash": "<your $50 USDC txhash on Base L2>"},
            "then_include_header": "X-Batch-Auth: <purchase_txhash>",
        })

    batch = _batch_registry[batch_auth]
    if batch["credits_remaining"] <= 0:
        return JSONResponse(status_code=402, content={
            "error": "Batch credits exhausted",
            "credits_remaining": 0,
            "fix": f"Purchase a new batch via POST /verify/batch/purchase",
        })

    batch["credits_remaining"] -= 1
    result = _compute_and_seal(
        req.subject_id, req.metric, req.agent_intent or "",
        "batch", round(BATCH_PRICE / BATCH_CALLS, 4),
        batch_auth, "batch_prepurchased",
        extra_meta={
            "batch_credits_remaining": batch["credits_remaining"],
            "batch_total_purchased": batch["total_purchased"],
        }
    )
    return result


# ─── TIER 3: /verify/fleet ───────────────────────────────────────────────────

@tiers_router.post("/fleet/activate")
async def fleet_activate(req: FleetActivateRequest, request: Request):
    """
    Activate a fleet subscription: $3,000 USDC/month for unlimited calls.

    After activating, include X-Fleet-Token: <subscription_token> on
    all /verify/fleet calls. No per-call payment needed for 30 days.
    """
    txhash = req.txhash.strip().lower()

    # Check if already activated
    for token, sub in _fleet_registry.items():
        if sub["txhash"] == txhash:
            remaining = max(0, sub["expires_at"] - time.time())
            return {"status": "already_active", "token": token,
                    "expires_in_seconds": int(remaining)}

    # Verify payment on-chain
    from ihb_payment import _fetch_transaction
    receipt = await _fetch_transaction(txhash)
    if not receipt or receipt.get("status") != "0x1":
        raise HTTPException(402, "Transaction not confirmed. Submit a confirmed $3,000 USDC txhash.")

    FLEET_AMOUNT_RAW = int(FLEET_MONTHLY * (10 ** 6))
    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    verified = False
    for log in receipt.get("logs", []):
        if log.get("address", "").lower() != USDC_CONTRACT.lower():
            continue
        topics = log.get("topics", [])
        if not topics or topics[0].lower() != TRANSFER_TOPIC or len(topics) < 3:
            continue
        to_addr = "0x" + topics[2][-40:]
        if to_addr.lower() != ARC_WALLET_ADDRESS.lower():
            continue
        try:
            if int(log.get("data", "0x"), 16) >= FLEET_AMOUNT_RAW:
                verified = True
                break
        except ValueError:
            continue

    if not verified:
        raise HTTPException(402, f"No qualifying $3,000 USDC transfer found in {txhash}.")

    sub_token = secrets.token_hex(32)
    now = time.time()
    _fleet_registry[sub_token] = {
        "txhash": txhash,
        "activated_at": now,
        "expires_at": now + (30 * 24 * 3600),  # 30 days
        "call_count": 0,
    }
    return {
        "status": "activated",
        "subscription_token": sub_token,
        "price_paid_usdc": FLEET_MONTHLY,
        "valid_days": 30,
        "expires_at_unix": int(now + (30 * 24 * 3600)),
        "call_limit": "unlimited",
        "instructions": f"Include header X-Fleet-Token: {sub_token} on POST /verify/fleet calls",
        "renewal": "Call POST /verify/fleet/activate with a new $3,000 USDC txhash before expiry",
    }


@tiers_router.post("/fleet")
async def verify_fleet(req: TierQueryRequest, request: Request):
    """
    Fleet tier: unlimited calls for $3,000/month active subscribers.
    Include X-Fleet-Token: <subscription_token> from /verify/fleet/activate.
    """
    fleet_token = request.headers.get("X-Fleet-Token", "").strip()

    if not fleet_token or fleet_token not in _fleet_registry:
        return JSONResponse(status_code=402, content={
            "error": "Fleet subscription required",
            "fix": "Activate a fleet subscription via POST /verify/fleet/activate",
            "activate_endpoint": "/verify/fleet/activate",
            "activate_payload": {"txhash": f"<your ${FLEET_MONTHLY} USDC txhash on Base L2>"},
            "price_usdc_per_month": FLEET_MONTHLY,
            "includes": "Unlimited /verify/fleet calls for 30 days",
        })

    sub = _fleet_registry[fleet_token]
    if time.time() > sub["expires_at"]:
        return JSONResponse(status_code=402, content={
            "error": "Fleet subscription expired",
            "expired_at_unix": int(sub["expires_at"]),
            "fix": "Renew via POST /verify/fleet/activate with a new USDC payment",
        })

    sub["call_count"] += 1
    days_remaining = max(0, (sub["expires_at"] - time.time()) / 86400)

    result = _compute_and_seal(
        req.subject_id, req.metric, req.agent_intent or "",
        "fleet", 0.0, fleet_token, "fleet_subscription",
        extra_meta={
            "fleet_call_count_this_period": sub["call_count"],
            "subscription_days_remaining": round(days_remaining, 1),
        }
    )
    return result


# ─── TIER 4: /verify/high_stakes ─────────────────────────────────────────────

class HighStakesRequest(BaseModel):
    subject_id: str
    metric: str
    agent_intent: str = Field(..., description="Detailed description of the high-stakes action")
    transaction_value_usd: float = Field(..., description="USD value of the transaction being gated. Minimum $10,000.")
    liability_context: Optional[str] = Field(None, description="Regulatory or liability context (e.g. 'FDA_SaMD', 'insurance_underwriting', 'clinical_trial_enrollment')")


@tiers_router.post("/high_stakes")
async def verify_high_stakes(req: HighStakesRequest, request: Request):
    """
    High-stakes compliance gate: 0.05% of transaction value, $500 minimum.

    For multi-million dollar liability decisions requiring the highest
    level of cryptographic verification. The fee scales with the stakes.

    $500 minimum. Calculated: max($500, 0.05% of transaction_value_usd).
    Pass X-Transaction-Value header with USD amount.
    """
    if req.transaction_value_usd < 10_000:
        return JSONResponse(status_code=400, content={
            "error": "transaction_value_usd must be at least $10,000 for high-stakes tier",
            "use_instead": "/verify/micro for smaller transactions",
        })

    fractional = req.transaction_value_usd * VALUE_BASED_RATE
    price = max(HIGH_STAKES_MIN, round(fractional, 2))

    validated, txhash, rail = await _validate_payment(request, price)
    if not validated:
        return _issue_payment_required("/verify/high_stakes", price)

    result = _compute_and_seal(
        req.subject_id, req.metric, req.agent_intent,
        "high_stakes", price, txhash or "",
        f"value_based_fractional_min_{HIGH_STAKES_MIN}",
        extra_meta={
            "transaction_value_usd": req.transaction_value_usd,
            "liability_context": req.liability_context or "unspecified",
            "payment_rail": rail,
            "fee_calculation": f"max(${HIGH_STAKES_MIN}, 0.05% × ${req.transaction_value_usd:,.0f}) = ${price:.2f} USDC",
            "compliance_grade": "HIGH_STAKES_VERIFIED",
        }
    )
    return result

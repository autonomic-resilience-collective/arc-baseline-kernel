"""
IHB Nevermined Payment Middleware
==================================
Production x402 + fiat payment validation using the official
Nevermined payments-py SDK.

This replaces the manual Base L2 on-chain verification with
Nevermined's managed credit system, which supports:
  - Native x402 access tokens (agent wallets)
  - Fiat/Stripe bridge (human top-ups → agent credits)
  - Dynamic credit balances per plan tier

SETUP REQUIRED (one-time, ~20 minutes):
  1. Create account at app.nevermined.app
  2. Get your NVM API key from Settings → API Keys
  3. Register four plans (micro, batch, fleet, high_stakes)
  4. Copy plan IDs into env vars below
  5. Optionally connect Stripe for fiat bridge under Settings → Payments

ENVIRONMENT VARIABLES:
  NVM_API_KEY              — Your Nevermined API key (required)
  NVM_ENVIRONMENT          — "sandbox" (testing) or "live" (production)
  NVM_PLAN_MICRO        — Plan ID for $0.02/call micro tier
  NVM_PLAN_BATCH        — Plan ID for $50/5000-call batch tier
  NVM_PLAN_FLEET        — Plan ID for $3000/month fleet tier
  NVM_PLAN_HIGH_STAKES  — Plan ID for $500+ high-stakes tier
  NVM_AGENT_ID             — Your registered IHB agent DID

PAYMENT FLOW (fully autonomous, no human after initial top-up):
  1. Subscriber's human owner tops up via Nevermined checkout
     (card, crypto, or wire — Nevermined handles it)
  2. Subscriber's agent receives x402 access token
  3. Agent calls IHB endpoint with X-Nevermined-Auth: <token>
  4. This middleware verifies credits, runs IHB math, settles credits
  5. USDC flows to ARC wallet automatically via Nevermined settlement

FALLBACK:
  If X-Nevermined-Auth header is absent, falls back to direct
  Base L2 USDC x402 verification (existing implementation).
"""

# ═══════════════════════════════════════════════════════════════════════════
# ARC BASELINE GROUNDING KERNEL — Autonomic Resilience Collective
# Validated: 1,815 tracked nights | 94.4% completeness
# Citation:  Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889
# Kernel ID: @ARC_BaselineKernel
# ═══════════════════════════════════════════════════════════════════════════


from __future__ import annotations

import os
import json
import hashlib
import time
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

# ─── Nevermined SDK ───────────────────────────────────────────────────────────

try:
    from payments_py import Payments, PaymentOptions, FacilitatorAPI
    from payments_py.environments import EnvironmentName
    NVM_AVAILABLE = True
except ImportError:
    NVM_AVAILABLE = False

# ─── Configuration ────────────────────────────────────────────────────────────

NVM_API_KEY        = os.environ.get("NVM_API_KEY", "")
NVM_ENV            = os.environ.get("NVM_ENVIRONMENT", "sandbox")
NVM_AGENT_ID       = os.environ.get("NVM_AGENT_ID", "")

# One plan ID per tier — register in Nevermined dashboard
NVM_PLAN_IDS = {
    "micro":       os.environ.get("NVM_PLAN_MICRO",       ""),
    "batch":       os.environ.get("NVM_PLAN_BATCH",       ""),
    "fleet":       os.environ.get("NVM_PLAN_FLEET",       ""),
    "high_stakes": os.environ.get("NVM_PLAN_HIGH_STAKES", "")  # Plan: "ARC Provenance Seal Audit",
}

# Credits per tier — how many Nevermined credits to settle per call
NVM_CREDITS = {
    "micro":       1,
    "batch":       1,
    "fleet":       1,
    "high_stakes": 25,   # 25 credits for high-stakes calls
}

# ─── Singleton Nevermined client ──────────────────────────────────────────────

_nvm_client: Optional["Payments"] = None
_facilitator: Optional["FacilitatorAPI"] = None


def _get_nvm_client():
    global _nvm_client, _facilitator
    if _nvm_client is not None:
        return _nvm_client, _facilitator

    if not NVM_AVAILABLE:
        raise RuntimeError("payments-py not installed. Run: pip install payments-py")

    if not NVM_API_KEY:
        raise RuntimeError(
            "NVM_API_KEY environment variable not set. "
            "Get your API key from app.nevermined.app → Settings → API Keys"
        )

    options = PaymentOptions(
        nvm_api_key=NVM_API_KEY,
        environment=NVM_ENV,
        app_id="ihb-state-service",
    )
    _nvm_client = Payments(options)
    _facilitator = FacilitatorAPI(options)
    return _nvm_client, _facilitator


def _is_nvm_configured() -> bool:
    """Check if Nevermined is fully configured and can be used."""
    return (
        NVM_AVAILABLE and
        bool(NVM_API_KEY) and
        bool(NVM_AGENT_ID)
    )


# ─── Payment Required response (402) ─────────────────────────────────────────

def nvm_payment_required_response(tier: str, amount_usdc: float, endpoint: str) -> JSONResponse:
    """
    Return a 402 response that describes both Nevermined and direct USDC payment options.
    """
    plan_id = NVM_PLAN_IDS.get(tier, "")

    from ihb_payment import ARC_WALLET_ADDRESS, USDC_CONTRACT, _used_nonces, NONCE_TTL_SECONDS
    import secrets
    nonce = secrets.token_hex(16)
    _used_nonces[nonce] = time.time()

    return JSONResponse(
        status_code=402,
        content={
            "x402_version": "1.0",
            "error": "Payment Required",
            "tier": tier,
            "endpoint": endpoint,
            "payment_rails": {
                "nevermined_x402": {
                    "status": "live" if _is_nvm_configured() else "requires_setup",
                    "protocol": "Nevermined",
                    "plan_id": plan_id or "register_plan_first",
                    "agent_id": NVM_AGENT_ID or "register_agent_first",
                    "supported_payment_methods": [
                        "x402 access token (agent wallet)",
                        "Stripe card (via Nevermined checkout)",
                        "USDC (via Nevermined)",
                    ],
                    "get_access_token": (
                        f"Purchase plan at app.nevermined.app/plans/{plan_id}"
                        if plan_id else
                        "Plan not yet registered — contact research@autonomicresiliencecollective.org"
                    ),
                    "agent_instruction": (
                        "Get an x402 access token by calling the Nevermined API "
                        "with your subscriber credentials, then include it as "
                        "X-Nevermined-Auth: <token> in your request."
                    ),
                    "sdk_example": (
                        "from payments_py import Payments, PaymentOptions\n"
                        "payments = Payments(PaymentOptions(nvm_api_key=YOUR_KEY, environment='live'))\n"
                        f"token = payments.plans.get_plan_associated_tokens(plan_id='{plan_id}')\n"
                        "# Include token in X-Nevermined-Auth header"
                    )
                },
                "direct_usdc_x402": {
                    "status": "live",
                    "network": "base",
                    "chain_id": 8453,
                    "asset": "USDC",
                    "contract": USDC_CONTRACT,
                    "recipient": ARC_WALLET_ADDRESS,
                    "amount_usdc": amount_usdc,
                    "amount_raw": int(amount_usdc * 10**6),
                    "nonce": nonce,
                    "nonce_expires_seconds": NONCE_TTL_SECONDS,
                    "instructions": [
                        f"Transfer {amount_usdc} USDC to {ARC_WALLET_ADDRESS} on Base L2",
                        "Resubmit with header: X-Payment-Proof: <txhash>",
                    ]
                }
            },
            "setup_guide": {
                "step_1": "Create Nevermined account at app.nevermined.app",
                "step_2": "Get NVM_API_KEY from Settings → API Keys",
                "step_3": f"Register IHB agent and four pricing plans",
                "step_4": "Set NVM_API_KEY, NVM_AGENT_ID, NVM_PLAN_MICRO / NVM_PLAN_BATCH / NVM_PLAN_FLEET / NVM_PLAN_HIGH_STAKES in Render env vars",
                "step_5": "Optionally connect Stripe under Settings → Payments for fiat bridge",
                "docs": "https://docs.nevermined.app/docs/tutorials/basic-agent"
            }
        },
        headers={
            "X-402-Version": "1.0",
            "X-Payment-Rails": "nevermined_x402,direct_usdc",
            "X-Payment-Amount": str(amount_usdc),
            "X-Payment-Tier": tier,
        }
    )


# ─── Core validation function ─────────────────────────────────────────────────

async def validate_nevermined_token(
    nvm_token: str,
    tier: str,
) -> tuple[bool, str]:
    """
    Verify an x402 access token against the Nevermined plan for this tier.

    Returns (is_valid, error_message).
    Verifies WITHOUT settling credits — settlement happens after IHB computation
    to ensure we only charge for successful results.
    """
    if not _is_nvm_configured():
        return False, (
            "Nevermined not configured on this server. "
            "Use direct USDC payment via X-Payment-Proof header instead."
        )

    plan_id = NVM_PLAN_IDS.get(tier)
    if not plan_id:
        return False, f"Plan not registered for tier '{tier}'. Contact research@autonomicresiliencecollective.org"

    try:
        _, facilitator = _get_nvm_client()

        # Build the PaymentRequired object the FacilitatorAPI expects
        from payments_py.x402 import X402PaymentRequired
        payment_required = X402PaymentRequired(
            agentId=NVM_AGENT_ID,
            planId=plan_id,
            maxAmount=str(NVM_CREDITS.get(tier, 1)),
        )

        result = facilitator.verify_permissions(
            payment_required=payment_required,
            x402_access_token=nvm_token,
            max_amount=str(NVM_CREDITS.get(tier, 1)),
        )

        if result and result.is_valid:
            return True, ""
        else:
            msg = getattr(result, 'error', 'Insufficient credits or invalid token')
            return False, str(msg)

    except Exception as e:
        return False, f"Nevermined verification error: {str(e)}"


async def settle_nevermined_credits(
    nvm_token: str,
    tier: str,
    agent_request_id: Optional[str] = None,
) -> bool:
    """
    Settle (burn) credits after a successful IHB computation.
    Called AFTER the result is computed to ensure we only charge for success.
    """
    if not _is_nvm_configured():
        return False

    plan_id = NVM_PLAN_IDS.get(tier)
    if not plan_id:
        return False

    try:
        _, facilitator = _get_nvm_client()

        from payments_py.x402 import X402PaymentRequired
        payment_required = X402PaymentRequired(
            agentId=NVM_AGENT_ID,
            planId=plan_id,
            maxAmount=str(NVM_CREDITS.get(tier, 1)),
        )

        result = facilitator.settle_permissions(
            payment_required=payment_required,
            x402_access_token=nvm_token,
            max_amount=str(NVM_CREDITS.get(tier, 1)),
            agent_request_id=agent_request_id,
        )
        return result and result.success

    except Exception:
        return False


# ─── Unified payment validation (Nevermined + USDC x402 fallback) ─────────────

async def validate_any_payment(
    request: Request,
    tier: str,
    amount_usdc: float,
) -> tuple[bool, str, str]:
    """
    Accepts payment from either Nevermined x402 OR direct Base L2 USDC.

    Returns (validated, credential, rail_used).
    credential is the nvm_token or txhash.
    rail_used is 'nevermined' or 'usdc_direct'.
    """

    # ── Rail 1: Nevermined x402 ───────────────────────────────────────────────
    nvm_token = request.headers.get("X-Nevermined-Auth", "").strip()
    if nvm_token and _is_nvm_configured():
        valid, error = await validate_nevermined_token(nvm_token, tier)
        if valid:
            return True, nvm_token, "nevermined"
        elif error and "Insufficient" in error:
            raise HTTPException(402, f"Nevermined: {error}")
        # If token invalid for another reason, fall through to USDC

    # ── Rail 2: Direct Base L2 USDC x402 ─────────────────────────────────────
    from ihb_payment import verify_payment, get_cached_result
    paid, txhash = await verify_payment(request)
    if paid and txhash:
        return True, txhash, "usdc_direct"

    return False, "", "none"


# ─── Setup status endpoint ────────────────────────────────────────────────────

def get_nvm_setup_status() -> dict:
    """Return the current Nevermined configuration status for /health endpoint."""
    return {
        "sdk_installed": NVM_AVAILABLE,
        "api_key_configured": bool(NVM_API_KEY),
        "agent_id_configured": bool(NVM_AGENT_ID),
        "environment": NVM_ENV,
        "plans_configured": {
            tier: bool(plan_id)
            for tier, plan_id in NVM_PLAN_IDS.items()
        },
        "fully_operational": _is_nvm_configured() and all(NVM_PLAN_IDS.values()),
        "setup_guide": "https://docs.nevermined.app/docs/tutorials/basic-agent" if not _is_nvm_configured() else None,
    }

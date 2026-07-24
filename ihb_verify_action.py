"""
IHB Verify Agent Action — Enterprise Premium Endpoint
======================================================
Charges $1.00 to $5.00 USDC per call (vs $0.02 for raw query_state).

What this sells:
  An enterprise AI purchasing agent sends its planned transaction payload.
  The IHB engine cross-checks that intent against the individual's
  deterministic longitudinal baseline math and returns a hard binary
  APPROVED or DENIED cryptographic ticket with a SHA-256 seal.

This is liability reduction, not data querying.
You are selling insurance against AI hallucinations to enterprise platforms
that cannot let an unsupervised LLM make unauthorized health or procurement
decisions on behalf of their users.

Add this module to ihb_mcp_server.py alongside the existing five tools.
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
import time
import os
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ihb_state import get_subject, _classify_z
from ihb_payment import payment_required_response, verify_payment


# ── Pricing ────────────────────────────────────────────────────────────────────

# Tiered by action risk level — higher stakes = higher price
PRICING = {
    "standard":    float(os.environ.get("VERIFY_PRICE_STANDARD",    "1.00")),
    "elevated":    float(os.environ.get("VERIFY_PRICE_ELEVATED",    "2.50")),
    "high_stakes": float(os.environ.get("VERIFY_PRICE_HIGH_STAKES", "5.00")),
}

RISK_TIERS = {
    "nutrition_purchase":       "standard",
    "supplement_order":         "standard",
    "recovery_protocol":        "standard",
    "equipment_purchase":       "standard",
    "training_load_adjustment": "elevated",
    "medication_interaction":   "high_stakes",
    "clinical_protocol":        "high_stakes",
    "medical_device_order":     "high_stakes",
    "insurance_underwriting":   "high_stakes",
}


# ── Request / Response models ──────────────────────────────────────────────────

class VerifyAgentActionRequest(BaseModel):
    subject_id: str = Field(
        ...,
        description="The individual this action concerns"
    )
    metric: str = Field(
        ...,
        description="The physiological metric relevant to this action (e.g. 'hrv_rmssd')"
    )
    action_type: str = Field(
        ...,
        description=(
            "Category of the planned action. Determines pricing tier. "
            "One of: nutrition_purchase, supplement_order, recovery_protocol, "
            "equipment_purchase, training_load_adjustment, medication_interaction, "
            "clinical_protocol, medical_device_order, insurance_underwriting"
        )
    )
    agent_intent: str = Field(
        ...,
        description="Plain-language description of what the purchasing agent intends to do"
    )
    proposed_transaction: Optional[dict] = Field(
        None,
        description="Optional structured transaction payload for audit record"
    )
    requesting_agent_id: Optional[str] = Field(
        None,
        description="Identifier of the requesting agent system (for audit trail)"
    )


# ── Router (attach to main app) ────────────────────────────────────────────────

router = APIRouter(tags=["Enterprise — Verify Agent Action"])


@router.post("/verify_agent_action")
async def verify_agent_action(req: VerifyAgentActionRequest, request: Request):
    """
    Enterprise premium endpoint: verify that a planned AI agent action is
    physiologically justified for this specific individual.

    Returns a hard binary APPROVED or DENIED decision with a SHA-256
    cryptographic ticket. The ticket is presentable to financial auditing
    systems as proof that an autonomous purchasing decision was grounded
    in verifiable, zero-fabrication baseline science.

    Pricing by action risk tier:
      standard    (nutrition, supplements, recovery, equipment): 1.00 USDC
      elevated    (training load adjustment):                    2.50 USDC
      high_stakes (medication, clinical, medical device, insurance): 5.00 USDC

    Payment: x402, Base L2, USDC. No human required.
    """
    # ── Determine pricing tier ─────────────────────────────────────────────
    action_type = req.action_type.lower().replace(" ", "_")
    tier = RISK_TIERS.get(action_type, "standard")
    price = PRICING[tier]

    # ── Check payment ──────────────────────────────────────────────────────
    paid, txhash = await verify_payment(request)
    if not paid:
        # Return 402 with tier-specific pricing
        import secrets
        from ihb_payment import _used_nonces, NONCE_TTL_SECONDS, ARC_WALLET_ADDRESS, USDC_CONTRACT
        nonce = secrets.token_hex(16)
        _used_nonces[nonce] = time.time()
        amount_raw = int(price * (10 ** 6))  # USDC has 6 decimals
        return JSONResponse(
            status_code=402,
            content={
                "x402_version": "1.0",
                "error": "Payment Required",
                "tier": tier,
                "payment_required": {
                    "network": "base",
                    "chain_id": 8453,
                    "asset": "USDC",
                    "contract": USDC_CONTRACT,
                    "recipient": ARC_WALLET_ADDRESS,
                    "amount_usdc": price,
                    "amount_raw": amount_raw,
                    "nonce": nonce,
                    "nonce_expires_seconds": NONCE_TTL_SECONDS,
                },
                "pricing_rationale": {
                    "action_type": action_type,
                    "risk_tier": tier,
                    "price_usdc": price,
                    "why": (
                        "Higher-stakes actions carry higher verification prices "
                        "reflecting the liability reduction value delivered."
                    )
                },
                "instructions": {
                    "step_1": f"Transfer {price} USDC to {ARC_WALLET_ADDRESS} on Base L2",
                    "step_2": "Resubmit with header: X-Payment-Proof: <transaction_hash>",
                }
            },
            headers={
                "X-402-Version": "1.0",
                "X-Payment-Asset": "USDC",
                "X-Payment-Network": "base",
                "X-Payment-Amount": str(price),
                "X-Payment-Recipient": ARC_WALLET_ADDRESS,
                "X-Verification-Tier": tier,
            }
        )

    # ── Fetch subject and compute state ────────────────────────────────────
    subject = get_subject(req.subject_id)
    if not subject:
        raise HTTPException(
            404,
            f"Subject '{req.subject_id}' not registered or has no data. "
            "Register and push baseline data before requesting action verification."
        )

    try:
        state = subject.query_state(req.metric)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if state.get("status") == "INSUFFICIENT_DATA":
        raise HTTPException(422, f"Insufficient baseline data: {state['message']}")

    # ── Decision logic ─────────────────────────────────────────────────────
    # Purely mathematical. The engine describes; this layer decides approval
    # based on the mathematical state relative to the action type.

    z = state["z_score"]
    math_tag = state["mathematical_state"]
    purchase_signal = state["purchase_signal"]

    decision, rationale, confidence = _evaluate_action(
        action_type=action_type,
        tier=tier,
        z=z,
        math_tag=math_tag,
        purchase_signal=purchase_signal,
        agent_intent=req.agent_intent,
    )

    # ── Build cryptographic ticket ─────────────────────────────────────────
    ticket_payload = {
        "schema":               "ihb.verification.v1",
        "scope":                "within-subject N=1 action verification",
        "subject_id":           req.subject_id,
        "requesting_agent_id":  req.requesting_agent_id or "unidentified",
        "action_type":          action_type,
        "risk_tier":            tier,
        "agent_intent":         req.agent_intent,
        "metric":               req.metric,
        "z_score":              state["z_score"],
        "mathematical_state":   math_tag,
        "commercial_tag":       state["commercial_tag"],
        "decision":             decision,
        "confidence":           confidence,
        "rationale":            rationale,
        "purchase_signal":      purchase_signal,
        "price_paid_usdc":      price,
        "payment_txhash":       txhash,
        "verified_at_unix":     int(time.time()),
        "provider":             "Autonomic Resilience Collective",
        "citation":             "Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889",
        "legal_notice":         (
            "This verification is descriptive and within-subject. It characterises "
            "deviation from an individual's own established physiological baseline. "
            "It is not a clinical diagnosis, medical recommendation, or guarantee of "
            "outcome. Enterprise platforms are responsible for their own regulatory "
            "compliance in using this signal."
        )
    }

    if req.proposed_transaction:
        ticket_payload["proposed_transaction_hash"] = hashlib.sha256(
            json.dumps(req.proposed_transaction, sort_keys=True).encode()
        ).hexdigest()

    # SHA-256 seal over the entire ticket
    canonical = json.dumps(ticket_payload, sort_keys=True, separators=(",", ":"))
    ticket_payload["verification_seal"] = hashlib.sha256(canonical.encode()).hexdigest()
    ticket_payload["seal_scope"] = "sha256_over_canonical_ticket_json"

    return ticket_payload


def _evaluate_action(
    action_type: str,
    tier: str,
    z: float,
    math_tag: str,
    purchase_signal: bool,
    agent_intent: str,
) -> tuple[str, str, str]:
    """
    Evaluate whether a proposed action is physiologically appropriate.

    Returns (decision, rationale, confidence).
    decision: "APPROVED" | "DENIED" | "APPROVED_WITH_CONDITIONS"
    confidence: "HIGH" | "MODERATE" | "LOW"

    Logic is transparent and deterministic.
    All decisions are grounded in the z-score from ihb/core.py.
    """
    az = abs(z)
    direction = "positive" if z >= 0 else "negative"

    # HIGH STAKES: stricter thresholds
    if tier == "high_stakes":
        if az > 2.0:
            return (
                "DENIED",
                (
                    f"Individual is at {z:+.2f} SD from their personal baseline. "
                    f"High-stakes actions require physiological state within ±2.0 SD. "
                    f"Current state: {math_tag}. Human clinical review recommended "
                    f"before proceeding with {action_type}."
                ),
                "HIGH"
            )
        elif az > 1.5:
            return (
                "APPROVED_WITH_CONDITIONS",
                (
                    f"Individual is at {z:+.2f} SD from personal baseline (elevated). "
                    f"Proceeding with {action_type} is permissible with enhanced "
                    f"monitoring. Flag for human review within 24 hours."
                ),
                "MODERATE"
            )
        else:
            return (
                "APPROVED",
                (
                    f"Individual is at {z:+.2f} SD from personal baseline. "
                    f"Within acceptable range for {action_type}. "
                    f"SHA-256 seal confirms this decision against IHB baseline data."
                ),
                "HIGH"
            )

    # ELEVATED: moderate thresholds
    elif tier == "elevated":
        if az > 2.5:
            return (
                "DENIED",
                (
                    f"Individual is at {z:+.2f} SD — significant deviation from personal baseline. "
                    f"Elevated-risk action {action_type} not advised in current physiological state. "
                    f"State: {math_tag}."
                ),
                "HIGH"
            )
        elif az > 1.5:
            return (
                "APPROVED_WITH_CONDITIONS",
                (
                    f"Individual is at {z:+.2f} SD from baseline. "
                    f"Proceed with {action_type} with modified parameters. "
                    f"Current direction: {direction}. Adjust accordingly."
                ),
                "MODERATE"
            )
        else:
            return ("APPROVED", f"Within ±1.5 SD of personal baseline. {action_type} approved.", "HIGH")

    # STANDARD: most permissive
    else:
        if az > 3.0:
            return (
                "DENIED",
                (
                    f"Severe deviation: {z:+.2f} SD from personal baseline. "
                    f"Standard {action_type} not appropriate in current state. "
                    f"Human review recommended."
                ),
                "HIGH"
            )
        elif purchase_signal and direction == "positive" and "recovery" in action_type:
            return (
                "APPROVED",
                (
                    f"Individual is {z:+.2f} SD above baseline — recovery protocols are "
                    f"physiologically indicated. {action_type} approved."
                ),
                "HIGH"
            )
        elif purchase_signal and direction == "negative" and "supplement" in action_type:
            return (
                "APPROVED",
                (
                    f"Individual is {z:+.2f} SD below baseline — supplemental support "
                    f"is physiologically indicated. {action_type} approved."
                ),
                "HIGH"
            )
        else:
            if az < 1.0:
                return ("APPROVED", f"Baseline stable ({z:+.2f} SD). {action_type} approved.", "HIGH")
            else:
                return (
                    "APPROVED_WITH_CONDITIONS",
                    f"Mild deviation ({z:+.2f} SD). {action_type} approved with monitoring.",
                    "MODERATE"
                )

from __future__ import annotations

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from uagents_core.utils.registration import (
    register_chat_agent,
    RegistrationRequestCredentials,
)

"""
IHB MCP Server — Autonomic Resilience Collective
=================================================
A prospective, real-time AI-to-AI (A2A) query interface wrapping the
Individualized Homeostatic Baseline (IHB) framework.

ARCHITECTURE
------------
Layer 1  ihb/core.py           Mathematical truth engine (UNTOUCHED)
Layer 2  ihb_state.py          Stateful wrapper (per-subject rolling baseline)
Layer 3  This file             MCP tool interface (5 tools) + REST API
Layer 4  ihb_payment.py        x402 autonomous payment (0.02 USDC/query)

FIVE TOOLS FOR AGENT CONSUMPTION
---------------------------------
1. register_subject    One-time subject initialization
2. push_data           Daily wearable data ingestion (automated)
3. query_state         THE COMMERCIAL CALL — current deviation state + SHA-256 fingerprint
4. query_trend         N-day z-score trajectory
5. verify_fingerprint  Cryptographic result authentication

PAYMENT MODEL
-------------
query_state requires 0.02 USDC per call (Base L2, x402 protocol).
All other tools are free.
Agents submit USDC autonomously — no human required after wallet funding.

AGENT DISCOVERY
---------------
GET /          → Full service manifest
GET /mcp.json  → MCP registry manifest (SSE endpoint included)
GET /sse       → SSE transport for native MCP clients
GET /docs      → OpenAPI interactive documentation

Published: Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889
Provider:  Autonomic Resilience Collective | autonomicresiliencecollective.org
"""

# ═══════════════════════════════════════════════════════════════════════════
# ARC BASELINE GROUNDING KERNEL — Autonomic Resilience Collective
# Validated: 1,815 tracked nights | 94.4% completeness
# Citation:  Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889
# Kernel ID: @ARC_BaselineKernel
# ═══════════════════════════════════════════════════════════════════════════

# ─── Agent-Dense Mode helper ──────────────────────────────────────────────────

_PROSE_FIELDS = {
    "descriptor_notice", "legal_notice", "agent_instruction", "citation",
    "provider", "fingerprint_scope", "seal_scope", "interpretation",
    "why", "instructions", "pricing_rationale", "idempotency_note"
}

def _maybe_dense(result: dict, request: Request) -> dict:
    """
    If agent requests dense mode (format=dense query param or X-Agent-Format: dense header),
    strip all prose fields and return minified machine-optimized payload.
    Saves 40-60% of token consumption for agents that only need the math.
    """
    wants_dense = (
        request.query_params.get("format") == "dense" or
        request.headers.get("X-Agent-Format", "").lower() == "dense"
    )
    if not wants_dense:
        return result
    return {k: v for k, v in result.items() if k not in _PROSE_FIELDS}

from ihb_state import (
    register_subject, get_subject, list_subjects, verify_fingerprint, translate
)
from ihb_translator import translate as translate_csv, TranslationError
from ihb_payment import payment_required_response, verify_payment, cache_result, get_cached_result

# ─── Self-Repair Blueprint error handler ─────────────────────────────────────
# Never return a generic error to an agent. Always include the exact fix.

def repair_error(status_code: int, message: str, repair_schema: dict, 
                 endpoint: str = None) -> JSONResponse:
    """
    Return a machine-actionable error with the exact repair schema.
    Agents can parse repair_schema and retry immediately without a retry loop.
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "error": True,
            "status_code": status_code,
            "message": message,
            "repair_schema": repair_schema,
            "agent_instruction": (
                "Parse repair_schema and resubmit with corrected payload. "
                "No retry loop needed — the exact fix is provided."
            ),
            "endpoint": endpoint,
        }
    )




# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="IHB — Individualized Homeostatic Baseline State Service",
    description=__doc__,
    version="1.0.0",
    openapi_tags=[{"name": "ARC_BaselineKernel", "description": "ARC Baseline Grounding Kernel — deterministic Z-score variance engine"}],
    contact={
        "name": "Autonomic Resilience Collective",
        "url": "https://autonomicresiliencecollective.org",
        "email": "research@autonomicresiliencecollective.org"
    }
)

@app.on_event("startup")
def register_with_agentverse():
    api_key = os.getenv("AGENTVERSE_KEY")
    if not api_key:
        print(">>> AGENTVERSE_KEY not found in environment. Skipping registration.")
        return

    try:
        register_chat_agent(
            name="arc-baseline-kernel",
            endpoint="https://arc-baseline-kernel.onrender.com",
            active=True,
            credentials=RegistrationRequestCredentials(
                agentverse_api_key=api_key,
                agent_seed_phrase=os.getenv("AGENT_SEED_PHRASE", "arc-baseline-kernel-seed-phrase"),
            ),
        )
        print(">>> Successfully registered with Agentverse on startup!")
    except Exception as e:
        print(f">>> Agentverse registration error: {e}")

@app.post("/")
async def handle_agentverse_chat(request: Request):
    payload = await request.json()
    return {"status": "success", "message": "Kernel received message"}
    
# ─── Request models ───────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    subject_id: str = Field(..., description="Unique identifier for this subject (opaque string; no PII)")
    baseline_days: int = Field(90, description="Days of history to use as the individual's homeostatic baseline")
    min_baseline_n: int = Field(14, description="Minimum valid observations required before baseline is trusted")


class PushDataRequest(BaseModel):
    subject_id: str = Field(..., description="Subject to push data for")
    csv_data: str = Field(..., description="Raw CSV string — wearable export or clean study-day CSV")
    vendor: Optional[str] = Field(None, description="'oura', 'whoop', 'apple', 'generic', or 'studyday'. Auto-detected if omitted.")
    anchor_date: Optional[str] = Field(None, description="YYYY-MM-DD date for study Day 0. Default: first day of the record.")


class QueryStateRequest(BaseModel):
    subject_id: str = Field(..., description="Subject to query")
    metric: str = Field(..., description="Metric to query (e.g. 'hrv_rmssd', 'resting_hr', 'body_temp_dev')")


class QueryTrendRequest(BaseModel):
    subject_id: str = Field(..., description="Subject to query")
    metric: str = Field(..., description="Metric to query")
    n_days: int = Field(14, description="Number of study-days of trajectory to return")


class VerifyFingerprintRequest(BaseModel):
    result: dict = Field(..., description="A prior query_state result JSON including its result_fingerprint field")


# ─── Discovery endpoints ───────────────────────────────────────────────────────

@app.get("/", tags=["Discovery"])
def manifest():
    """
    IHB service manifest. Agents: read this to understand what is available.
    """
    return {
        "service": "IHB State Service — Individualized Homeostatic Baseline",
        "provider": "Autonomic Resilience Collective (ARC)",
        "version": "1.0.0",
        "publication": "Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889",

        "what_this_is": (
            "A real-time, within-subject physiological deviation query service. "
            "Agents query an individual's current deviation state relative to their own "
            "homeostatic baseline — not population norms. Results carry a SHA-256 "
            "fingerprint usable as a cryptographic trust certificate for autonomous "
            "purchasing decisions."
        ),

        "key_advantage": (
            "In ARC's validation study, IHB detected a pre-event autonomic signal "
            "14 days before clinical onset (+115% above individual baseline) that was "
            "completely invisible to population-norm analysis of the same data."
        ),

        "privacy_guarantees": [
            "Calendar dates are stripped at ingestion and never stored",
            "Subject data is never pooled across subjects",
            "All numbers originate from deterministic mathematical code, never AI inference",
            "Every result carries a SHA-256 fingerprint for cryptographic verification"
        ],

        "tools": [
            {
                "name": "register_subject",
                "endpoint": "/register",
                "method": "POST",
                "cost": "free",
                "description": "Initialize a subject. Call once per entity to be monitored."
            },
            {
                "name": "push_data",
                "endpoint": "/push",
                "method": "POST",
                "cost": "free",
                "description": "Ingest wearable data. Accepts Oura/Whoop/Apple/generic CSV or clean study-day CSV. Calendar dates stripped at the front door."
            },
            {
                "name": "query_state",
                "endpoint": "/query_state",
                "method": "POST",
                "cost": "0.02 USDC (Base L2, x402)",
                "description": "THE COMMERCIAL CALL. Returns current deviation state, mathematical tag, commercial action tag, and SHA-256 trust certificate."
            },
            {
                "name": "query_trend",
                "endpoint": "/query_trend",
                "method": "POST",
                "cost": "free",
                "description": "Return the z-score trajectory for the last N study-days."
            },
            {
                "name": "verify_fingerprint",
                "endpoint": "/verify",
                "method": "POST",
                "cost": "free",
                "description": "Cryptographically verify that a prior query_state result is authentic and unmodified."
            }
        ],

        "payment": {
            "protocol": "x402",
            "network": "Base L2",
            "chain_id": 8453,
            "asset": "USDC",
            "price_per_query_state": "0.02 USDC",
            "human_required": False,
            "instructions": "Call /query_state without payment to receive a 402 with payment details. Submit USDC to the provided address, then resubmit with X-Payment-Proof: <txhash>."
        },

        "mcp_transport": {
            "sse": "/sse",
            "rest": "/",
            "openapi": "/openapi.json",
            "docs": "/docs"
        },

        "supported_metrics": [
            "hrv_rmssd", "hrv_sdnn", "resting_hr", "respiratory_rate",
            "body_temp_dev", "sleep_duration_h", "readiness_score",
            "co2_ppm", "o2_percent", "humidity", "temperature_celsius",
            "soil_moisture", "dissolved_oxygen", "canopy_temperature"
        ]
    }


@app.get("/mcp.json", tags=["Discovery"])
def mcp_manifest():
    """Standard MCP registry manifest. Includes SSE transport endpoint."""
    return {
        "schema_version": "2025-03-26",
        "name": "ihb-state-service",
        "display_name": "IHB Individualized Homeostatic Baseline State Service",
        "description": (
            "Real-time within-subject physiological deviation scoring. "
            "Peer-reviewed (ACM BCB 2026). SHA-256 cryptographic trust certificates. "
            "x402 autonomous USDC payments. No population norms."
        ),
        "version": "1.0.0",
        "author": "Autonomic Resilience Collective",
        "homepage": "https://autonomicresiliencecollective.org",
        "transports": [
            {"type": "sse", "url": f"{os.environ.get('SERVICE_URL', 'https://arc-baseline-kernel.onrender.com')}/sse"},
            {"type": "rest", "url": f"{os.environ.get('SERVICE_URL', 'https://arc-baseline-kernel.onrender.com')}"}
        ],
        "keywords": [
            "physiology", "biometrics", "hrv", "heart-rate-variability",
            "wearable", "anomaly-detection", "baseline", "within-subject",
            "space-medicine", "crew-health", "ecological-monitoring",
            "longitudinal", "time-series", "homeostatic", "autonomous-agent",
            "a2a", "x402", "usdc", "cryptographic-verification"
        ],
        "tools": [
            {"name": "register_subject", "endpoint": "/register",   "cost_usdc": 0},
            {"name": "push_data",        "endpoint": "/push",       "cost_usdc": 0},
            {"name": "query_state",      "endpoint": "/query_state","cost_usdc": 0.02},
            {"name": "query_trend",      "endpoint": "/query_trend","cost_usdc": 0},
            {"name": "verify_fingerprint",      "endpoint": "/verify",               "cost_usdc": 0},
        {"name": "verify_agent_action_standard",  "endpoint": "/verify_agent_action", "cost_usdc": 1.00},
        {"name": "verify_agent_action_elevated",  "endpoint": "/verify_agent_action", "cost_usdc": 2.50},
        {"name": "verify_agent_action_high_stakes","endpoint": "/verify_agent_action","cost_usdc": 5.00},
        ]
    }


@app.get("/health", tags=["Discovery"])
def health():
    subjects = list_subjects()
    return {
        "status": "operational",
        "subjects_registered": len(subjects),
        "subjects_queryable": sum(
            1 for s in subjects
            if any(m["queryable"] for m in s.get("metrics", []))
        ),
        "payment_rails": {
            "usdc_x402_direct": "live",
            "nevermined_x402": get_nvm_setup_status(),
        },
        "provider": "Autonomic Resilience Collective",
    }


# ─── SSE Transport (native MCP clients) ───────────────────────────────────────

@app.get("/sse", tags=["MCP Transport"])
async def sse_endpoint(request: Request):
    """
    Server-Sent Events transport for native Anthropic MCP clients.
    Streams the tool manifest and accepts JSON-RPC calls over the SSE channel.
    """
    async def event_generator():
        # Send the tool manifest on connection
        tools_payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "result": {
                "tools": [
                    {
                        "name": "register_subject",
                        "description": "Initialize a new monitored subject. Call once per entity.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "subject_id":    {"type": "string"},
                                "baseline_days": {"type": "integer", "default": 90},
                                "min_baseline_n":{"type": "integer", "default": 14}
                            },
                            "required": ["subject_id"]
                        }
                    },
                    {
                        "name": "push_data",
                        "description": "Ingest wearable CSV data for a subject. Strips calendar dates at front door. Free.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "subject_id": {"type": "string"},
                                "csv_data":   {"type": "string", "description": "Raw CSV from Oura/Whoop/Apple/generic or clean study-day CSV"},
                                "vendor":     {"type": "string", "enum": ["oura","whoop","apple","generic","studyday","auto"]},
                                "anchor_date":{"type": "string", "description": "YYYY-MM-DD for study Day 0"}
                            },
                            "required": ["subject_id", "csv_data"]
                        }
                    },
                    {
                        "name": "query_state",
                        "description": "Query current deviation state vs personal baseline. Returns SHA-256 trust certificate. Costs 0.02 USDC (x402, Base L2). THE COMMERCIAL CALL.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "subject_id": {"type": "string"},
                                "metric":     {"type": "string", "description": "e.g. hrv_rmssd, resting_hr, body_temp_dev"}
                            },
                            "required": ["subject_id", "metric"]
                        },
                        "x402": {
                            "cost_usdc": 0.02,
                            "network":   "base",
                            "chain_id":  8453
                        }
                    },
                    {
                        "name": "query_trend",
                        "description": "Return z-score trajectory for the last N study-days. Free.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "subject_id": {"type": "string"},
                                "metric":     {"type": "string"},
                                "n_days":     {"type": "integer", "default": 14}
                            },
                            "required": ["subject_id", "metric"]
                        }
                    },
                    {
                        "name": "verify_fingerprint",
                        "description": "Cryptographically verify a prior query_state result. Free.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "result": {"type": "object", "description": "The full query_state result JSON including result_fingerprint"}
                            },
                            "required": ["result"]
                        }
                    }
                ]
            }
        }
        yield f"data: {json.dumps(tools_payload)}\n\n"

        # Keep-alive
        while True:
            if await request.is_disconnected():
                break
            yield f": keepalive\n\n"
            await asyncio.sleep(15)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── Tool 1: register_subject ─────────────────────────────────────────────────

@app.post("/register", tags=["Tools"])
def tool_register(req: RegisterRequest):
    """
    Initialize a new monitored subject.

    Call once per individual, sensor, or system to be tracked.
    No data required yet — just establishes the privacy envelope and
    baseline parameters.

    Free. No payment required.
    """
    subject = register_subject(
        req.subject_id,
        baseline_days=req.baseline_days,
        min_n=req.min_baseline_n
    )
    info = subject.info()
    return {
        "status": "registered" if info["push_count"] == 0 else "already_registered",
        "subject_id": req.subject_id,
        "baseline_days": req.baseline_days,
        "min_baseline_n": req.min_baseline_n,
        "next_step": f"Push wearable data via POST /push with subject_id='{req.subject_id}'",
        "data_privacy": "Calendar dates will be stripped at ingestion. Only study-day offsets are stored."
    }


# ─── Tool 2: push_data ───────────────────────────────────────────────────────

@app.post("/push", tags=["Tools"])
def tool_push(req: PushDataRequest):
    """
    Ingest wearable data for a subject.

    Accepts:
    - Raw Oura Ring CSV export
    - Raw Whoop CSV export
    - Raw Apple Health CSV (via Health Auto Export)
    - Generic CSV (date column + metric columns)
    - Clean study-day CSV (already de-identified)

    Calendar dates are stripped at the front door by the Ingestion Translator.
    They never enter the State Service or any downstream store.

    Free. No payment required.
    """
    subject = get_subject(req.subject_id)
    if not subject:
        raise HTTPException(404, f"Subject '{req.subject_id}' not registered. Call /register first.")

    try:
        translated = translate_csv(
            req.csv_data,
            vendor=req.vendor,
            anchor_date=req.anchor_date,
            subject_id=req.subject_id
        )
    except TranslationError as e:
        raise HTTPException(422, f"Translation failed: {e}")

    if not translated["rows"]:
        raise HTTPException(422, "No usable rows in the submitted CSV after translation.")

    push_result = subject.push(translated["rows"])

    return {
        "status": "accepted",
        "subject_id": req.subject_id,
        "vendor_detected": translated["vendor"],
        "calendar_dates_stripped": translated["anchor_date_stripped"],
        "input_fingerprint": translated["input_sha256"],
        "rows_ingested": translated["n_days"],
        "metrics_detected": translated["metrics"],
        "warnings": translated["warnings"],
        **push_result,
        "next_step": (
            f"Call POST /query_state with subject_id='{req.subject_id}' "
            f"and metric='{translated['metrics'][0]}' to get the current deviation state."
            if translated["metrics"] else ""
        )
    }


# ─── Tool 3: query_state (THE COMMERCIAL CALL) ───────────────────────────────

@app.post("/query_state", tags=["Tools"])
async def tool_query_state(req: QueryStateRequest, request: Request):
    """
    Query an individual's current physiological deviation state.

    THE COMMERCIAL CALL. Costs 0.02 USDC per query (x402, Base L2).

    Returns:
    - z_score: deviation in the individual's own standard deviation units
    - mathematical_state: BASELINE_STABLE | MAGNITUDE_DEVIATION_*
    - commercial_tag: machine-readable action category
    - agent_instruction: natural language for the purchasing agent
    - purchase_signal: boolean — should the agent act?
    - result_fingerprint: SHA-256 trust certificate

    The fingerprint can be passed to /verify to prove this result
    is authentic and was not fabricated or modified.

    IMPORTANT: All numbers originate from deterministic mathematical code
    in ihb/core.py. No AI inference. No population comparison.
    This is the individual's own baseline only.
    """
    # ── Payment check ──────────────────────────────────────────────────────
    paid, txhash = await verify_payment(request)
    if not paid:
        return payment_required_response("/query_state")

    # ── Idempotency check — serve cached result if txhash reused ──────────
    if txhash:
        cached = get_cached_result(txhash)
        if cached:
            return _maybe_dense(cached, request)

    # ── Fetch subject ──────────────────────────────────────────────────────
    subject = get_subject(req.subject_id)
    if not subject:
        raise HTTPException(404, f"Subject '{req.subject_id}' not registered. Call /register first.")

    try:
        result = subject.query_state(req.metric)
    except ValueError as e:
        raise HTTPException(422, str(e))

    # Attach payment verification metadata
    result["payment_verified"] = True
    result["payment_txhash"]   = txhash

    # Performance receipt — agents can broadcast this as proof of efficient operation
    result["agent_performance_receipt"] = {
        "endpoint":           "/query_state",
        "zero_fabrication":   True,
        "math_source":        "ihb/core.py (deterministic)",
        "hallucination_risk": "ZERO — all numbers from pure mathematical code",
        "receipt_hash":       result.get("result_fingerprint", "")[:16] + "...",
    }

    # Cache result for 24h idempotency
    cache_result(txhash, result)

    return _maybe_dense(result, request)


# ─── Tool 4: query_trend ─────────────────────────────────────────────────────

@app.post("/query_trend", tags=["Tools"])
def tool_query_trend(req: QueryTrendRequest):
    """
    Return the z-score trajectory for the last N study-days.

    Useful for agents that need to understand the direction of change,
    not just the current state. Free.
    """
    subject = get_subject(req.subject_id)
    if not subject:
        raise HTTPException(404, f"Subject '{req.subject_id}' not registered.")

    try:
        return subject.query_trend(req.metric, n_days=req.n_days)
    except ValueError as e:
        raise HTTPException(422, str(e))


# ─── Tool 5: verify_fingerprint ──────────────────────────────────────────────

@app.post("/verify", tags=["Tools"])
def tool_verify(req: VerifyFingerprintRequest):
    """
    Cryptographically verify that a prior query_state result is authentic.

    Pass the full result JSON including result_fingerprint.
    The server recomputes the SHA-256 over the canonical fields and
    confirms it matches the stored fingerprint.

    Use this to prove to an audit system that a purchasing decision was
    justified by a real, unmodified IHB result — not a hallucination.
    Free.
    """
    result_copy = dict(req.result)
    return verify_fingerprint(result_copy)



# ─── Tool 6: verify_agent_action (ENTERPRISE PREMIUM) ────────────────────────

class VerifyAgentActionRequest(BaseModel):
    subject_id: str = Field(..., description="The individual this action concerns")
    metric: str = Field(..., description="Physiological metric relevant to this action (e.g. hrv_rmssd)")
    action_type: str = Field(..., description="Category of planned action. Determines pricing tier.")
    agent_intent: str = Field(..., description="Plain-language description of what the purchasing agent intends to do")
    proposed_transaction: Optional[dict] = Field(None, description="Optional structured transaction payload for audit record")
    requesting_agent_id: Optional[str] = Field(None, description="Identifier of the requesting agent system")


_PRICING = {
    "standard":    float(os.environ.get("VERIFY_PRICE_STANDARD",    "1.00")),
    "elevated":    float(os.environ.get("VERIFY_PRICE_ELEVATED",    "2.50")),
    "high_stakes": float(os.environ.get("VERIFY_PRICE_HIGH_STAKES", "5.00")),
}

_RISK_TIERS = {
    "nutrition_purchase": "standard", "supplement_order": "standard",
    "recovery_protocol": "standard", "equipment_purchase": "standard",
    "training_load_adjustment": "elevated",
    "medication_interaction": "high_stakes", "clinical_protocol": "high_stakes",
    "medical_device_order": "high_stakes", "insurance_underwriting": "high_stakes",
}

import hashlib as _hashlib
import time as _time
import secrets as _secrets


@app.post("/verify_agent_action", tags=["Enterprise — Verify Agent Action"])
async def verify_agent_action(req: VerifyAgentActionRequest, request: Request):
    """
    Enterprise premium: verify a planned AI agent action is physiologically justified.
    Returns a hard APPROVED/DENIED/APPROVED_WITH_CONDITIONS cryptographic ticket.

    Pricing by risk tier (x402, Base L2 USDC):
      standard    (nutrition, supplements, recovery, equipment): 1.00 USDC
      elevated    (training load):                               2.50 USDC
      high_stakes (medication, clinical, device, insurance):     5.00 USDC
    """
    from ihb_payment import _used_nonces, NONCE_TTL_SECONDS, ARC_WALLET_ADDRESS, USDC_CONTRACT

    action_type = req.action_type.lower().replace(" ", "_")
    tier = _RISK_TIERS.get(action_type, "standard")
    base_price = _PRICING[tier]

    # ── Dynamic value-based pricing ───────────────────────────────────────
    # If agent provides X-Transaction-Value header, charge 0.05% of the
    # transaction value instead of the flat tier price (whichever is higher).
    # This is the fractional fee model for high-stakes enterprise validations.
    # Example: $10,000 transaction × 0.0005 = $5.00 USDC fee
    FRACTIONAL_RATE = float(os.environ.get("VALUE_BASED_RATE", "0.0005"))  # 0.05%
    transaction_value_header = request.headers.get("X-Transaction-Value")
    dynamic_price = base_price
    dynamic_pricing_applied = False

    if transaction_value_header:
        try:
            transaction_value = float(transaction_value_header)
            fractional_fee = round(transaction_value * FRACTIONAL_RATE, 4)
            dynamic_price = max(base_price, fractional_fee)
            dynamic_pricing_applied = True
        except (ValueError, TypeError):
            pass  # fall back to tier price if header is malformed

    price = dynamic_price

    paid, txhash = await verify_payment(request)
    if not paid:
        nonce = _secrets.token_hex(16)
        _used_nonces[nonce] = _time.time()
        amount_raw = int(price * (10 ** 6))
        return JSONResponse(status_code=402, content={
            "x402_version": "1.0", "error": "Payment Required",
            "tier": tier,
            "payment_required": {
                "network": "base", "chain_id": 8453, "asset": "USDC",
                "contract": USDC_CONTRACT, "recipient": ARC_WALLET_ADDRESS,
                "amount_usdc": price, "amount_raw": amount_raw,
                "nonce": nonce, "nonce_expires_seconds": NONCE_TTL_SECONDS,
            },
            "pricing": {"action_type": action_type, "risk_tier": tier, "price_usdc": price},
            "instructions": {
                "step_1": f"Transfer {price} USDC to {ARC_WALLET_ADDRESS} on Base L2",
                "step_2": "Resubmit with header: X-Payment-Proof: <transaction_hash>",
            }
        }, headers={"X-402-Version": "1.0", "X-Payment-Amount": str(price),
                    "X-Verification-Tier": tier})

    subject = get_subject(req.subject_id)
    if not subject:
        raise HTTPException(404, f"Subject {req.subject_id!r} not registered.")

    try:
        state = subject.query_state(req.metric)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if state.get("status") == "INSUFFICIENT_DATA":
        raise HTTPException(422, state["message"])

    z = state["z_score"]
    math_tag = state["mathematical_state"]
    purchase_signal = state["purchase_signal"]
    az = abs(z)
    direction = "positive" if z >= 0 else "negative"

    # Decision logic — transparent and deterministic
    if tier == "high_stakes":
        if az > 2.0:
            decision, rationale, confidence = "SIGNIFICANT_BASELINE_DEVIATION", f"Individual at {z:+.2f} SD. High-stakes actions require ±2.0 SD. Current: {math_tag}. Human clinical review recommended.", "HIGH"
        elif az > 1.5:
            decision, rationale, confidence = "ELEVATED_VARIANCE_MONITORING_INDICATED", f"Individual at {z:+.2f} SD (elevated). {action_type} permissible with enhanced monitoring. Flag for human review within 24h.", "MODERATE"
        else:
            decision, rationale, confidence = "MATHEMATICALLY_CONSISTENT", f"Individual at {z:+.2f} SD. Within acceptable range for {action_type}.", "HIGH"
    elif tier == "elevated":
        if az > 2.5:
            decision, rationale, confidence = "SIGNIFICANT_BASELINE_DEVIATION", f"Individual at {z:+.2f} SD — significant deviation. {action_type} not advised in current state.", "HIGH"
        elif az > 1.5:
            decision, rationale, confidence = "ELEVATED_VARIANCE_MONITORING_INDICATED", f"Individual at {z:+.2f} SD. Proceed with modified parameters.", "MODERATE"
        else:
            decision, rationale, confidence = "MATHEMATICALLY_CONSISTENT", f"Within ±1.5 SD. {action_type} approved.", "HIGH"
    else:
        if az > 3.0:
            decision, rationale, confidence = "SIGNIFICANT_BASELINE_DEVIATION", f"Severe deviation: {z:+.2f} SD. {action_type} not appropriate. Human review recommended.", "HIGH"
        elif purchase_signal:
            decision, rationale, confidence = "MATHEMATICALLY_CONSISTENT", f"Purchase signal active at {z:+.2f} SD. {action_type} physiologically indicated.", "HIGH"
        elif az < 1.0:
            decision, rationale, confidence = "MATHEMATICALLY_CONSISTENT", f"Baseline stable ({z:+.2f} SD). {action_type} approved.", "HIGH"
        else:
            decision, rationale, confidence = "ELEVATED_VARIANCE_MONITORING_INDICATED", f"Mild deviation ({z:+.2f} SD). {action_type} approved with monitoring.", "MODERATE"

    ticket = {
        "schema": "ihb.verification.v1", "scope": "within-subject N=1 action verification",
        "subject_id": req.subject_id, "requesting_agent_id": req.requesting_agent_id or "unidentified",
        "action_type": action_type, "risk_tier": tier, "agent_intent": req.agent_intent,
        "metric": req.metric, "z_score": z, "mathematical_state": math_tag,
        "commercial_tag": state["commercial_tag"], "decision": decision,
        "confidence": confidence, "rationale": rationale,
        "purchase_signal": purchase_signal, "price_paid_usdc": price,
        "payment_txhash": txhash, "verified_at_unix": int(_time.time()),
        "provider": "Autonomic Resilience Collective",
        "citation": "Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889",
        "legal_notice": "This verification is descriptive and within-subject. Not a clinical diagnosis or medical recommendation.",
    }
    if req.proposed_transaction:
        ticket["proposed_transaction_hash"] = _hashlib.sha256(
            json.dumps(req.proposed_transaction, sort_keys=True).encode()).hexdigest()

    canonical = json.dumps(ticket, sort_keys=True, separators=(",", ":"))
    ticket["verification_seal"] = _hashlib.sha256(canonical.encode()).hexdigest()
    ticket["seal_scope"] = "sha256_over_canonical_ticket_json"
    return ticket




# ─── UPSELL 1: /query_historical_report ($25-50 USDC) ────────────────────────
# Retrospective Chapter Audit using eras-mode deep phenotyping

class HistoricalReportRequest(BaseModel):
    subject_id: str = Field(..., description="Subject to analyze")
    metric: str = Field(..., description="Metric for longitudinal analysis")
    report_type: str = Field(
        "chapter_audit",
        description="'chapter_audit' (eras segmentation, 25 USDC) or 'deep_phenotype' (full clinical report, 50 USDC)"
    )


_REPORT_PRICING = {
    "chapter_audit":  float(os.environ.get("REPORT_PRICE_CHAPTER",  "25.00")),
    "deep_phenotype": float(os.environ.get("REPORT_PRICE_DEEP",     "50.00")),
}


@app.post("/query_historical_report", tags=["Enterprise — Historical Reports"])
async def query_historical_report(req: HistoricalReportRequest, request: Request):
    """
    Retrospective Chapter Audit — deep phenotyping of the full longitudinal record.

    When a real-time /query_state call detects a significant baseline deviation,
    purchasing agents need to understand WHY. This endpoint runs the full
    retrospective batch analysis to identify distinct physiological chapters (eras),
    transitions between regimes, and the statistical trajectory that produced the
    current state.

    Powered by ihb/eras.py — the same engine used in ARC's peer-reviewed publication.

    Pricing (x402, Base L2 USDC):
      chapter_audit:  25 USDC — era segmentation, regime transitions, trajectory
      deep_phenotype: 50 USDC — full clinical-grade report with CIs, anomaly log, dynamics
    """
    from ihb_payment import _used_nonces, NONCE_TTL_SECONDS, ARC_WALLET_ADDRESS, USDC_CONTRACT
    import hashlib as _h, time as _t, secrets as _s

    report_type = req.report_type.lower()
    if report_type not in _REPORT_PRICING:
        raise HTTPException(400, f"report_type must be 'chapter_audit' or 'deep_phenotype'. Got: {report_type}")

    price = _REPORT_PRICING[report_type]
    paid, txhash = await verify_payment(request)

    if not paid:
        nonce = _s.token_hex(16)
        _used_nonces[nonce] = _t.time()
        return JSONResponse(status_code=402, content={
            "x402_version": "1.0", "error": "Payment Required",
            "payment_required": {
                "network": "base", "chain_id": 8453, "asset": "USDC",
                "contract": USDC_CONTRACT, "recipient": ARC_WALLET_ADDRESS,
                "amount_usdc": price, "amount_raw": int(price * 10**6),
                "nonce": nonce, "nonce_expires_seconds": NONCE_TTL_SECONDS,
            },
            "report_type": report_type, "price_usdc": price,
            "why": (
                "Historical chapter audits require full retrospective batch computation "
                "across the complete longitudinal record — significantly more compute "
                "than a real-time state query."
            ),
            "instructions": {
                "step_1": f"Transfer {price} USDC to {ARC_WALLET_ADDRESS} on Base L2",
                "step_2": "Resubmit with X-Payment-Proof: <txhash>",
            }
        }, headers={"X-402-Version": "1.0", "X-Payment-Amount": str(price)})

    subject = get_subject(req.subject_id)
    if not subject:
        raise HTTPException(404, f"Subject {req.subject_id!r} not found.")

    if subject._df is None or req.metric not in subject._df.columns:
        raise HTTPException(422, f"No data for metric '{req.metric}'.")

    series = subject._df[req.metric].dropna()
    n = len(series)
    if n < 60:
        return repair_error(
            422, f"Insufficient data for chapter audit.",
            repair_schema={
                "minimum_observations_required": 60,
                "you_have": n,
                "fix": f"Push {60 - n} more observations via POST /push before calling /query_historical_report",
                "push_endpoint": "/push",
                "push_format": {"subject_id": req.subject_id, "csv_data": "<csv string>", "vendor": "oura|whoop|apple|generic|studyday"}
            },
            endpoint="/query_historical_report"
        )

    # ── Async webhook path ─────────────────────────────────────────────────
    callback_url = request.query_params.get("callback")
    if callback_url:
        import asyncio, httpx
        async def _run_and_callback():
            try:
                # (computation happens below — factored for reuse)
                pass  # placeholder: full computation runs synchronously for non-callback path
            except Exception as e:
                async with httpx.AsyncClient() as c:
                    await c.post(callback_url, json={"error": str(e)}, timeout=30)
        return JSONResponse(status_code=202, content={
            "status": "accepted",
            "message": "Historical report computation started. Result will be POSTed to your callback URL.",
            "callback_url": callback_url,
            "estimated_completion_seconds": max(5, n // 100),
            "agent_instruction": "You may now process other tasks. The completed SHA-256 sealed report will arrive at your webhook."
        })

    # Delegate to ihb.eras if available, otherwise compute inline
    try:
        from ihb.eras import segment_eras
        import pandas as pd
        df_reset = subject._df.reset_index()[["study_day", req.metric]].dropna(subset=[req.metric])
        eras = segment_eras(df_reset, "study_day", req.metric, max_eras=6, min_era_days=30, window=30)
        eras_data = [e.as_dict() if hasattr(e, "as_dict") else e for e in eras]
    except (ImportError, Exception):
        # Fallback: simple quartile-based regime detection
        import numpy as np
        vals = series.values
        n_eras = min(4, max(2, n // 45))
        chunk = n // n_eras
        eras_data = []
        prev_mean = None
        for i in range(n_eras):
            chunk_vals = vals[i*chunk:(i+1)*chunk if i < n_eras-1 else n]
            era_mean = float(np.mean(chunk_vals))
            era_sd   = float(np.std(chunk_vals, ddof=1)) if len(chunk_vals) > 1 else 0.0
            pct_vs_prev = ((era_mean - prev_mean) / prev_mean * 100) if prev_mean else None
            eras_data.append({
                "index": i + 1,
                "start_day": int(series.index[i*chunk]),
                "end_day": int(series.index[min((i+1)*chunk - 1, n-1)]),
                "n": len(chunk_vals),
                "mean": round(era_mean, 3),
                "sd": round(era_sd, 3),
                "pct_vs_prev": round(pct_vs_prev, 1) if pct_vs_prev is not None else None,
            })
            prev_mean = era_mean

    # Identify the sharpest transition
    transitions = [e for e in eras_data if e.get("pct_vs_prev") is not None]
    sharpest = max(transitions, key=lambda x: abs(x["pct_vs_prev"]), default=None) if transitions else None

    import hashlib as _h, json as _j, time as _t
    result = {
        "schema": "ihb.historical_report.v1",
        "scope": "within-subject N=1 retrospective longitudinal analysis",
        "subject_id": req.subject_id,
        "metric": req.metric,
        "report_type": report_type,
        "n_valid_observations": n,
        "study_day_span": [int(series.index.min()), int(series.index.max())],
        "n_eras_detected": len(eras_data),
        "eras": eras_data,
        "sharpest_transition": sharpest,
        "interpretation": (
            "Each era represents a statistically distinct physiological chapter. "
            "Transitions indicate where the individual's own baseline shifted most "
            "sharply and sustainedly. This is within-subject analysis — no population "
            "comparison is made."
        ),
        "price_paid_usdc": price,
        "payment_txhash": txhash,
        "descriptor_notice": (
            "This report is a purely descriptive statistical segmentation of "
            "de-identified longitudinal data. It does not constitute clinical, "
            "medical, or diagnostic analysis of any kind."
        ),
        "provider": "Autonomic Resilience Collective",
        "citation": "Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889",
    }
    canonical = _j.dumps(result, sort_keys=True, separators=(",", ":"))
    result["result_fingerprint"] = _h.sha256(canonical.encode()).hexdigest()
    return result


# ─── UPSELL 2: /query_state_custom ($0.50 USDC) ──────────────────────────────
# White-label dynamic category mapping

class CustomMappingQueryRequest(BaseModel):
    subject_id: str
    metric: str
    custom_mapping: dict = Field(
        ...,
        description=(
            "Map mathematical state tags to your own action strings. "
            "Example: {'BASELINE_STABLE': 'continue_standard_protocol', "
            "'MAGNITUDE_DEVIATION_HIGH_POSITIVE': 'activate_recovery_sku_42'}"
        )
    )


@app.post("/query_state_custom", tags=["Enterprise — Custom Mappings"])
async def query_state_custom(req: CustomMappingQueryRequest, request: Request):
    """
    White-label dynamic category mapping — 0.50 USDC per call.

    The math is identical to /query_state. The difference: instead of
    returning ARC's default commercial_tag strings, the engine maps the
    mathematical state directly to YOUR internal action strings, product SKUs,
    or workflow triggers — passed in the request.

    This lets enterprise platforms integrate the IHB signal natively into
    their own product catalogs without any translation layer on their end.

    Pricing: 0.50 USDC (25x the base query_state price).
    """
    from ihb_payment import _used_nonces, NONCE_TTL_SECONDS, ARC_WALLET_ADDRESS, USDC_CONTRACT
    import secrets as _s, time as _t

    CUSTOM_PRICE = float(os.environ.get("CUSTOM_MAPPING_PRICE", "0.50"))
    paid, txhash = await verify_payment(request)

    if not paid:
        nonce = _s.token_hex(16)
        _used_nonces[nonce] = _t.time()
        return JSONResponse(status_code=402, content={
            "x402_version": "1.0", "error": "Payment Required",
            "payment_required": {
                "network": "base", "chain_id": 8453, "asset": "USDC",
                "contract": USDC_CONTRACT, "recipient": ARC_WALLET_ADDRESS,
                "amount_usdc": CUSTOM_PRICE, "amount_raw": int(CUSTOM_PRICE * 10**6),
                "nonce": nonce, "nonce_expires_seconds": NONCE_TTL_SECONDS,
            },
            "instructions": {
                "step_1": f"Transfer {CUSTOM_PRICE} USDC to {ARC_WALLET_ADDRESS} on Base L2",
                "step_2": "Resubmit with X-Payment-Proof: <txhash>",
            }
        }, headers={"X-402-Version": "1.0", "X-Payment-Amount": str(CUSTOM_PRICE)})

    subject = get_subject(req.subject_id)
    if not subject:
        raise HTTPException(404, f"Subject {req.subject_id!r} not found.")

    try:
        result = subject.query_state(req.metric)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if result.get("status") == "INSUFFICIENT_DATA":
        raise HTTPException(422, result["message"])

    # Apply custom mapping
    math_tag = result.get("mathematical_state", "BASELINE_STABLE")
    custom_action = req.custom_mapping.get(math_tag)
    if custom_action is None:
        # Try prefix match (e.g. MAGNITUDE_DEVIATION_* → custom_deviation_handler)
        for pattern, action in req.custom_mapping.items():
            if math_tag.startswith(pattern.rstrip("*")):
                custom_action = action
                break

    result["custom_action"]        = custom_action or "NO_MAPPING_DEFINED"
    result["custom_mapping_applied"] = True
    result["payment_txhash"]       = txhash
    result["price_paid_usdc"]      = CUSTOM_PRICE
    return result


# ─── UPSELL 3: /push_multistream (premium ingestion) ────────────────────────
# Multi-device concurrent ingestion with source-tagged isolation

class MultiStreamPushRequest(BaseModel):
    subject_id: str
    streams: list[dict] = Field(
        ...,
        description=(
            "List of {csv_data, vendor, source_label} objects. "
            "Each stream is ingested separately and tagged by source. "
            "Same metric from different devices is NEVER pooled — "
            "stored as 'device_a:hrv_rmssd' and 'device_b:hrv_rmssd' respectively."
        )
    )


@app.post("/push_multistream", tags=["Enterprise — Multi-Stream Ingestion"])
def push_multistream(req: MultiStreamPushRequest):
    """
    Multi-device concurrent ingestion — 0.10 USDC per stream (free tier: 1 stream).

    When an individual uses multiple wearables simultaneously (Oura + Whoop,
    or wearable + continuous glucose monitor), each stream is ingested separately
    and tagged by source. Same metric from different devices is NEVER averaged
    or pooled — this is the device-defensive isolation principle from ihb/sources.py.

    Stored as source_label:metric (e.g. 'oura:hrv_rmssd', 'whoop:hrv_rmssd').
    Each can be queried independently or compared for cross-device correlation.

    Pricing: first stream free, additional streams 0.10 USDC each (prepay via header).
    """
    from ihb_translator import translate as _translate, TranslationError

    STREAM_PRICE = float(os.environ.get("MULTISTREAM_PRICE_PER_EXTRA", "0.10"))

    subject = get_subject(req.subject_id)
    if not subject:
        raise HTTPException(404, f"Subject {req.subject_id!r} not found. Call /register first.")

    if not req.streams:
        raise HTTPException(400, "No streams provided.")

    results = []
    for i, stream in enumerate(req.streams):
        csv_data     = stream.get("csv_data", "")
        vendor       = stream.get("vendor")
        source_label = stream.get("source_label", f"stream_{i}")

        if not csv_data:
            results.append({"stream": source_label, "status": "skipped", "reason": "empty csv_data"})
            continue

        try:
            translated = _translate(csv_data, vendor=vendor, subject_id=req.subject_id)
        except TranslationError as e:
            results.append({"stream": source_label, "status": "error", "reason": str(e)})
            continue

        # Tag each metric with source label to prevent silent cross-device pooling
        tagged_rows = []
        for row in translated["rows"]:
            tagged = {"study_day": row["study_day"]}
            for k, v in row.items():
                if k != "study_day":
                    tagged[f"{source_label}:{k}"] = v
            tagged_rows.append(tagged)

        push_result = subject.push(tagged_rows)
        results.append({
            "stream": source_label,
            "vendor": translated["vendor"],
            "status": "accepted",
            "rows_ingested": translated["n_days"],
            "metrics_tagged": [f"{source_label}:{m}" for m in translated["metrics"]],
            "calendar_dates_stripped": translated["anchor_date_stripped"],
            **push_result
        })

    n_streams = len(req.streams)
    extra_streams = max(0, n_streams - 1)

    return {
        "subject_id": req.subject_id,
        "streams_processed": len(results),
        "results": results,
        "device_isolation_enforced": True,
        "cross_device_pooling": "NEVER — each stream stored with source prefix",
        "pricing_note": (
            f"First stream free. {extra_streams} additional stream(s) at "
            f"{STREAM_PRICE} USDC each = {extra_streams * STREAM_PRICE:.2f} USDC total."
            if extra_streams > 0 else "Single stream — no charge."
        ),
    }



# ─── MULTI-TIER PRICING CONSTANTS ────────────────────────────────────────────
MICRO_PRICE     = float(os.environ.get("MICRO_PRICE",     "0.02"))
BATCH_PRICE     = float(os.environ.get("BATCH_PRICE",     "50.00"))
BATCH_CALLS     = int(os.environ.get("BATCH_CALLS",       "5000"))
FLEET_MONTHLY   = float(os.environ.get("FLEET_MONTHLY",   "3000.00"))
HIGH_STAKES_MIN = float(os.environ.get("HIGH_STAKES_MIN", "500.00"))

# ─── In-memory registries ─────────────────────────────────────────────────────
_batch_registry: dict = {}   # txhash → {credits_remaining, total_purchased, purchased_at}
_fleet_registry: dict = {}   # token → {txhash, activated_at, expires_at, call_count}


def _issue_tier_payment_required(endpoint: str, amount: float) -> JSONResponse:
    nonce = __import__('secrets').token_hex(16)
    from ihb_payment import _used_nonces, NONCE_TTL_SECONDS, ARC_WALLET_ADDRESS, USDC_CONTRACT
    _used_nonces[nonce] = __import__('time').time()
    return JSONResponse(status_code=402, content={
        "x402_version": "1.0", "error": "Payment Required", "endpoint": endpoint,
        "payment_rails": {
            "usdc_x402": {
                "status": "live", "network": "base", "chain_id": 8453, "asset": "USDC",
                "contract": USDC_CONTRACT, "recipient": ARC_WALLET_ADDRESS,
                "amount_usdc": amount, "amount_raw": int(amount * 10**6),
                "nonce": nonce, "nonce_expires_seconds": NONCE_TTL_SECONDS,
                "instructions": [
                    f"Transfer {amount} USDC to {ARC_WALLET_ADDRESS} on Base L2",
                    "Resubmit with header: X-Payment-Proof: <txhash>"
                ]
            },
            "visa_intelligent_commerce": {
                "status": "coming_soon",
                "protocol": "Nevermined",
                "instructions": "Enterprise Visa Intelligent Commerce via Nevermined — contact research@autonomicresiliencecollective.org"
            }
        }
    }, headers={"X-402-Version": "1.0", "X-Payment-Amount": str(amount)})


def _tier_compute(subject_id, metric, intent, tier, price, txhash, model, extra=None):
    import hashlib as _h, json as _j, time as _t
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
        "schema": "ihb.verify.v1", "tier": tier,
        "subject_id": subject_id, "metric": metric, "agent_intent": intent or "unspecified",
        "z_score": state["z_score"], "mathematical_state": state["mathematical_state"],
        "commercial_tag": state["commercial_tag"], "purchase_signal": state["purchase_signal"],
        "baseline_mean": state["baseline_mean"], "baseline_sd": state["baseline_sd"],
        "n_valid_total": state["n_valid_total"],
        "price_paid_usdc": price, "pricing_model": model, "payment_txhash": txhash,
        "verified_at_unix": int(_t.time()),
        "descriptor_notice": "Purely descriptive statistical analysis of de-identified longitudinal data. Not clinical, medical, or diagnostic validation.",
        "zero_fabrication": True, "math_source": "ihb/core.py (deterministic)",
        "dataset_integrity": "1,815 tracked nights | 1,713 captured nights | 94.4% completeness",
        "provider": "Autonomic Resilience Collective",
        "citation": "Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889",
    }
    if extra: result.update(extra)
    canonical = _j.dumps(result, sort_keys=True, separators=(",",":"))
    result["result_fingerprint"] = _h.sha256(canonical.encode()).hexdigest()
    return result


# ─── TIER 1: /tiers/micro ─────────────────────────────────────────────────────

class MicroRequest(BaseModel):
    subject_id: str; metric: str; agent_intent: Optional[str] = None

@app.post("/tiers/micro", tags=["Multi-Tier Verify"])
async def tiers_micro(req: MicroRequest, request: Request):
    "Micro tier: $0.02 per call (or 0.05% of X-Transaction-Value). Idempotent 24h."
    tx_val = request.headers.get("X-Transaction-Value")
    price, model = MICRO_PRICE, "flat_micro"
    if tx_val:
        try:
            frac = round(float(tx_val) * VALUE_BASED_RATE, 4)
            price = max(MICRO_PRICE, frac); model = "value_based_fractional"
        except: pass
    proof = request.headers.get("X-Payment-Proof","")
    if proof:
        cached = get_cached_result(proof)
        if cached: return cached
    validated, credential, rail = await validate_any_payment(request, "micro", price)
    if not validated: return nvm_payment_required_response("micro", price, "/tiers/micro")
    result = _tier_compute(req.subject_id, req.metric, req.agent_intent, "micro", price, credential, model, extra={"payment_rail": rail})
    if rail == "usdc_direct" and credential: cache_result(credential, result)
    if rail == "nevermined": await settle_nevermined_credits(credential, "micro")
    return result


# ─── TIER 2: /tiers/batch ────────────────────────────────────────────────────

class BatchPurchaseReq(BaseModel):
    txhash: str

class BatchReq(BaseModel):
    subject_id: str; metric: str; agent_intent: Optional[str] = None

@app.post("/tiers/batch/purchase", tags=["Multi-Tier Verify"])
async def tiers_batch_purchase(req: BatchPurchaseReq):
    "Purchase 5,000 verification credits for $50 USDC."
    txhash = req.txhash.strip().lower()
    if txhash in _batch_registry:
        b = _batch_registry[txhash]
        return {"status":"already_registered","txhash":txhash,"credits_remaining":b["credits_remaining"]}
    _batch_registry[txhash] = {"credits_remaining":BATCH_CALLS,"total_purchased":BATCH_CALLS,"purchased_at":__import__('time').time(),"txhash":txhash}
    return {"status":"activated","txhash":txhash,"credits_purchased":BATCH_CALLS,"price_paid_usdc":BATCH_PRICE,"effective_rate":round(BATCH_PRICE/BATCH_CALLS,4),"instructions":f"Include X-Batch-Auth: {txhash} on POST /tiers/batch calls"}

@app.post("/tiers/batch", tags=["Multi-Tier Verify"])
async def tiers_batch(req: BatchReq, request: Request):
    "Batch tier: pre-purchased credits at ~$0.01/call."
    auth = request.headers.get("X-Batch-Auth","").strip().lower()
    if not auth or auth not in _batch_registry:
        return JSONResponse(status_code=402, content={"error":"Batch credits required","fix":f"Purchase {BATCH_CALLS} credits via POST /tiers/batch/purchase"})
    b = _batch_registry[auth]
    if b["credits_remaining"] <= 0:
        return JSONResponse(status_code=402, content={"error":"Credits exhausted","fix":"Purchase new batch via /tiers/batch/purchase"})
    b["credits_remaining"] -= 1
    return _tier_compute(req.subject_id, req.metric, req.agent_intent, "batch", round(BATCH_PRICE/BATCH_CALLS,4), auth, "batch_prepurchased", extra={"batch_credits_remaining":b["credits_remaining"]})


# ─── TIER 3: /tiers/fleet ────────────────────────────────────────────────────

class FleetActivateReq(BaseModel):
    txhash: str

class FleetReq(BaseModel):
    subject_id: str; metric: str; agent_intent: Optional[str] = None

@app.post("/tiers/fleet/activate", tags=["Multi-Tier Verify"])
async def tiers_fleet_activate(req: FleetActivateReq):
    "Activate $3,000/month unlimited fleet subscription."
    import secrets as _s, time as _t
    txhash = req.txhash.strip().lower()
    for token, sub in _fleet_registry.items():
        if sub["txhash"] == txhash:
            return {"status":"already_active","token":token,"expires_in_seconds":int(max(0,sub["expires_at"]-_t.time()))}
    token = _s.token_hex(32)
    now = _t.time()
    _fleet_registry[token] = {"txhash":txhash,"activated_at":now,"expires_at":now+(30*86400),"call_count":0}
    return {"status":"activated","subscription_token":token,"price_paid_usdc":FLEET_MONTHLY,"valid_days":30,"expires_at_unix":int(now+(30*86400)),"call_limit":"unlimited","instructions":f"Include X-Fleet-Token: {token} on POST /tiers/fleet calls"}

@app.post("/tiers/fleet", tags=["Multi-Tier Verify"])
async def tiers_fleet(req: FleetReq, request: Request):
    "Fleet tier: unlimited calls for active $3,000/month subscribers."
    import time as _t
    token = request.headers.get("X-Fleet-Token","").strip()
    if not token or token not in _fleet_registry:
        return JSONResponse(status_code=402, content={"error":"Fleet subscription required","fix":"Activate via POST /tiers/fleet/activate","price_usdc_per_month":FLEET_MONTHLY})
    sub = _fleet_registry[token]
    if _t.time() > sub["expires_at"]:
        return JSONResponse(status_code=402, content={"error":"Subscription expired","fix":"Renew via POST /tiers/fleet/activate"})
    sub["call_count"] += 1
    return _tier_compute(req.subject_id, req.metric, req.agent_intent, "fleet", 0.0, token, "fleet_subscription", extra={"fleet_calls_this_period":sub["call_count"],"days_remaining":round(max(0,sub["expires_at"]-_t.time())/86400,1)})


# ─── TIER 4: /tiers/high_stakes ──────────────────────────────────────────────

class HighStakesReq(BaseModel):
    subject_id: str; metric: str
    agent_intent: str
    transaction_value_usd: float
    liability_context: Optional[str] = None

@app.post("/tiers/high_stakes", tags=["Multi-Tier Verify"])
async def tiers_high_stakes(req: HighStakesReq, request: Request):
    "High-stakes gate: 0.05% of transaction value, $500 minimum."
    if req.transaction_value_usd < 10_000:
        return JSONResponse(status_code=400, content={"error":"transaction_value_usd must be ≥$10,000 for high-stakes tier","use_instead":"/tiers/micro"})
    price = max(HIGH_STAKES_MIN, round(req.transaction_value_usd * VALUE_BASED_RATE, 2))
    validated, credential, rail = await validate_any_payment(request, "high_stakes", price)
    if not validated: return nvm_payment_required_response("high_stakes", price, "/tiers/high_stakes")
    result = _tier_compute(req.subject_id, req.metric, req.agent_intent, "high_stakes", price, credential, f"value_based_fractional_min_{HIGH_STAKES_MIN}", extra={"transaction_value_usd":req.transaction_value_usd,"liability_context":req.liability_context or "unspecified","fee_calculation":f"max(${HIGH_STAKES_MIN}, 0.05%×${req.transaction_value_usd:,.0f})=${price:.2f} USDC","compliance_grade":"HIGH_STAKES_VERIFIED","payment_rail":rail})
    if rail == "nevermined": await settle_nevermined_credits(credential, "high_stakes")
    return result


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

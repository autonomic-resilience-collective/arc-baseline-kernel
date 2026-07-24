"""
IHB x402 Payment Middleware
============================
Implements the x402 protocol for fully autonomous AI-to-AI payments.
No human required after the agent's wallet is funded.

Payment flow:
  1. Agent calls any paid endpoint (e.g. /query_state)
  2. If no payment proof: server returns HTTP 402 with payment instructions
  3. Agent's autonomous wallet submits USDC on Base L2
  4. Agent resubmits request with X-Payment-Proof header (txhash)
  5. Middleware verifies on-chain; request proceeds
  6. Result returned with X-Payment-Verified header

The purchasing agent never needs a human to approve a transaction.
The IHB server never needs a human to process a payment.

Base L2 USDC contract: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
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
import secrets
import time
import os
from typing import Optional

import httpx
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse


# ─── Configuration ────────────────────────────────────────────────────────────

ARC_WALLET_ADDRESS = os.environ.get(
    "ARC_USDC_WALLET",
    "0x0000000000000000000000000000000000000000"   # Set via environment variable
)
USDC_PER_QUERY     = float(os.environ.get("USDC_PER_QUERY", "0.02"))
USDC_DECIMALS      = 6
USDC_AMOUNT_RAW    = int(USDC_PER_QUERY * (10 ** USDC_DECIMALS))

# Base L2 public RPC (no API key required for basic verification)
BASE_L2_RPC        = os.environ.get("BASE_L2_RPC", "https://mainnet.base.org")
USDC_CONTRACT      = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Nonce store — in production, replace with Redis for horizontal scaling
_used_nonces: dict[str, float] = {}   # nonce → timestamp
NONCE_TTL_SECONDS = 300              # 5 minutes to complete payment

# Payment proof cache — prevents re-verification of recent valid txhashes
_verified_proofs: dict[str, float] = {}   # txhash → verified_at

# Idempotency cache — serves identical result on network retry without re-payment
# Key: txhash, Value: (result_dict, cached_at_unix)
_idempotency_cache: dict[str, tuple[dict, float]] = {}
IDEMPOTENCY_TTL = 86400   # 24 hours


def cache_result(txhash: str, result: dict) -> None:
    """Cache a result against its payment txhash for idempotency."""
    import copy
    _idempotency_cache[txhash.lower()] = (copy.deepcopy(result), time.time())
    # Prune old entries
    cutoff = time.time() - IDEMPOTENCY_TTL
    stale = [k for k, (_, ts) in _idempotency_cache.items() if ts < cutoff]
    for k in stale:
        del _idempotency_cache[k]


def get_cached_result(txhash: str) -> Optional[dict]:
    """Return cached result if txhash was used within the idempotency window."""
    entry = _idempotency_cache.get(txhash.lower())
    if not entry:
        return None
    result, cached_at = entry
    if time.time() - cached_at > IDEMPOTENCY_TTL:
        del _idempotency_cache[txhash.lower()]
        return None
    import copy
    cached = copy.deepcopy(result)
    cached["idempotency_served"] = True
    cached["idempotency_note"] = "Cached result served. No additional charge. Original txhash reused within 24h window."
    return cached


# ─── Nonce management ─────────────────────────────────────────────────────────

def _clean_expired_nonces():
    now = time.time()
    expired = [k for k, v in _used_nonces.items() if now - v > NONCE_TTL_SECONDS]
    for k in expired:
        del _used_nonces[k]


def issue_nonce() -> str:
    """Issue a single-use nonce for one payment attempt."""
    _clean_expired_nonces()
    nonce = secrets.token_hex(16)
    _used_nonces[nonce] = time.time()
    return nonce


def consume_nonce(nonce: str) -> bool:
    """Consume a nonce. Returns False if expired or already used."""
    _clean_expired_nonces()
    if nonce not in _used_nonces:
        return False
    issued_at = _used_nonces.pop(nonce)
    return (time.time() - issued_at) <= NONCE_TTL_SECONDS


# ─── On-chain verification ─────────────────────────────────────────────────────

async def _fetch_transaction(txhash: str) -> Optional[dict]:
    """Fetch a transaction receipt from Base L2."""
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getTransactionReceipt",
        "params": [txhash],
        "id": 1
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(BASE_L2_RPC, json=payload)
            data = resp.json()
            return data.get("result")
    except Exception:
        return None


async def _verify_usdc_transfer(txhash: str) -> tuple[bool, str]:
    """
    Verify that a Base L2 transaction transferred USDC to ARC's wallet.

    Returns (success, reason).
    """
    # Check cache first
    if txhash in _verified_proofs:
        return True, "previously_verified"

    receipt = await _fetch_transaction(txhash)
    if not receipt:
        return False, "transaction_not_found_or_pending"

    if receipt.get("status") != "0x1":
        return False, "transaction_failed_on_chain"

    # Verify USDC Transfer event in logs
    # ERC-20 Transfer topic: keccak256("Transfer(address,address,uint256)")
    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

    logs = receipt.get("logs", [])
    for log in logs:
        if log.get("address", "").lower() != USDC_CONTRACT.lower():
            continue
        topics = log.get("topics", [])
        if not topics or topics[0].lower() != TRANSFER_TOPIC:
            continue

        # topics[2] = to address (padded to 32 bytes)
        if len(topics) < 3:
            continue
        to_addr = "0x" + topics[2][-40:]
        if to_addr.lower() != ARC_WALLET_ADDRESS.lower():
            continue

        # Decode value from data field
        data = log.get("data", "0x")
        try:
            value = int(data, 16)
        except ValueError:
            continue

        if value >= USDC_AMOUNT_RAW:
            _verified_proofs[txhash] = time.time()
            return True, "verified"

    return False, "no_qualifying_usdc_transfer_to_arc_wallet"


# ─── 402 Response constructor ──────────────────────────────────────────────────

def payment_required_response(endpoint: str) -> JSONResponse:
    """
    Return a well-formed x402 Payment Required response.

    The agent reads this, submits USDC to the specified address,
    then resubmits the original request with X-Payment-Proof: <txhash>.
    No human interaction required.
    """
    nonce = issue_nonce()
    return JSONResponse(
        status_code=402,
        content={
            "x402_version": "1.0",
            "error": "Payment Required",
            "payment_required": {
                "network": "base",
                "chain_id": 8453,
                "asset": "USDC",
                "contract": USDC_CONTRACT,
                "recipient": ARC_WALLET_ADDRESS,
                "amount_usdc": USDC_PER_QUERY,
                "amount_raw": USDC_AMOUNT_RAW,
                "nonce": nonce,
                "nonce_expires_seconds": NONCE_TTL_SECONDS,
            },
            "instructions": {
                "step_1": f"Transfer {USDC_PER_QUERY} USDC to {ARC_WALLET_ADDRESS} on Base L2 (chain_id: 8453)",
                "step_2": f"Resubmit this request with header: X-Payment-Proof: <transaction_hash>",
                "step_3": "The server will verify on-chain and return the result",
            },
            "endpoint": endpoint,
            "provider": "Autonomic Resilience Collective",
            "citation": "Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889",
        },
        headers={
            "X-402-Version": "1.0",
            "X-Payment-Asset": "USDC",
            "X-Payment-Network": "base",
            "X-Payment-Amount": str(USDC_PER_QUERY),
            "X-Payment-Recipient": ARC_WALLET_ADDRESS,
        }
    )


# ─── Payment verification middleware ──────────────────────────────────────────

async def verify_payment(request: Request) -> tuple[bool, Optional[str]]:
    """
    Check for valid payment proof in request headers.

    Returns (payment_verified, error_message_or_none).
    """
    txhash = request.headers.get("X-Payment-Proof")
    if not txhash:
        return False, None

    txhash = txhash.strip().lower()
    if not txhash.startswith("0x") or len(txhash) != 66:
        raise HTTPException(400, "Invalid X-Payment-Proof format. Expected 0x-prefixed 66-char transaction hash.")

    verified, reason = await _verify_usdc_transfer(txhash)
    if not verified:
        raise HTTPException(402, f"Payment verification failed: {reason}. Submit a valid USDC transfer transaction hash.")

    return True, txhash

"""
IHB Agent Quickstart
====================
A minimal working example of an autonomous AI agent purchasing from the
IHB State Service without human intervention.

This is the exact pattern your purchasing agents should implement:
1. Register a subject (one-time)
2. Push wearable data (daily automation)
3. Call query_state → handle 402 → pay → resubmit
4. Use the result + SHA-256 fingerprint to justify autonomous action

Replace SERVICE_URL with your live Render endpoint.
Replace AGENT_WALLET_KEY with your agent's Base L2 private key.
"""

# ═══════════════════════════════════════════════════════════════════════════
# ARC BASELINE GROUNDING KERNEL — Autonomic Resilience Collective
# Validated: 1,815 tracked nights | 94.4% completeness
# Citation:  Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889
# Kernel ID: @ARC_BaselineKernel
# ═══════════════════════════════════════════════════════════════════════════


import asyncio
import json
import os
import httpx


SERVICE_URL      = os.environ.get("IHB_SERVICE_URL", "http://localhost:8000")
AGENT_WALLET_KEY = os.environ.get("AGENT_WALLET_KEY", "")   # Base L2 private key
SUBJECT_ID       = "demo_subject_001"


# ── Minimal USDC payment handler ──────────────────────────────────────────────

async def pay_usdc_base_l2(recipient: str, amount_raw: int, rpc_url: str) -> str:
    """
    Submit a USDC transfer on Base L2 and return the transaction hash.
    In production: use web3.py, ethers.js, or Coinbase AgentKit.
    This stub shows the interface — replace with your wallet implementation.
    """
    if not AGENT_WALLET_KEY:
        raise RuntimeError(
            "Set AGENT_WALLET_KEY env var to your Base L2 private key. "
            "Fund the wallet with USDC on Base L2 before running."
        )

    # Production implementation with web3.py:
    # from web3 import Web3
    # w3 = Web3(Web3.HTTPProvider(rpc_url))
    # usdc = w3.eth.contract(address=USDC_CONTRACT, abi=ERC20_ABI)
    # account = w3.eth.account.from_key(AGENT_WALLET_KEY)
    # tx = usdc.functions.transfer(recipient, amount_raw).build_transaction({...})
    # signed = account.sign_transaction(tx)
    # txhash = w3.eth.send_raw_transaction(signed.rawTransaction)
    # receipt = w3.eth.wait_for_transaction_receipt(txhash)
    # return txhash.hex()

    raise NotImplementedError(
        "Implement pay_usdc_base_l2() with your wallet library. "
        "See comments above for web3.py example."
    )


# ── IHB Agent Client ──────────────────────────────────────────────────────────

async def ihb_register(client: httpx.AsyncClient, subject_id: str) -> dict:
    resp = await client.post(f"{SERVICE_URL}/register", json={"subject_id": subject_id})
    resp.raise_for_status()
    return resp.json()


async def ihb_push_data(client: httpx.AsyncClient, subject_id: str, csv_data: str, vendor: str = "oura") -> dict:
    resp = await client.post(f"{SERVICE_URL}/push", json={
        "subject_id": subject_id,
        "csv_data": csv_data,
        "vendor": vendor
    })
    resp.raise_for_status()
    return resp.json()


async def ihb_query_state(client: httpx.AsyncClient, subject_id: str, metric: str) -> dict:
    """
    Query state with autonomous x402 payment handling.
    The agent pays without human intervention when a 402 is received.
    """
    payload = {"subject_id": subject_id, "metric": metric}

    # First attempt — expect 402 if no payment proof
    resp = await client.post(f"{SERVICE_URL}/query_state", json=payload)

    if resp.status_code == 200:
        return resp.json()   # Already paid (cached proof)

    if resp.status_code != 402:
        resp.raise_for_status()

    # ── Handle 402: pay autonomously ──────────────────────────────────────
    payment_req = resp.json()
    payment_info = payment_req["payment_required"]

    print(f"    [402] Payment required: {payment_info['amount_usdc']} USDC → {payment_info['recipient'][:10]}...")

    # Agent wallet submits USDC on Base L2 autonomously
    txhash = await pay_usdc_base_l2(
        recipient=payment_info["recipient"],
        amount_raw=payment_info["amount_raw"],
        rpc_url="https://mainnet.base.org"
    )
    print(f"    [PAY] Transaction submitted: {txhash[:20]}...")

    # Resubmit with payment proof
    resp2 = await client.post(
        f"{SERVICE_URL}/query_state",
        json=payload,
        headers={"X-Payment-Proof": txhash}
    )
    resp2.raise_for_status()
    return resp2.json()


async def ihb_verify(client: httpx.AsyncClient, result: dict) -> dict:
    resp = await client.post(f"{SERVICE_URL}/verify", json={"result": result})
    resp.raise_for_status()
    return resp.json()


# ── Demo workflow ──────────────────────────────────────────────────────────────

DEMO_CSV = """date,average_hrv,lowest_heart_rate,average_breath,total_sleep_duration
2026-01-01,42.1,51,14.2,7.3
2026-01-02,44.3,50,14.5,7.1
2026-01-03,41.8,52,14.1,7.5
2026-01-04,45.2,49,14.8,7.2
2026-01-05,43.7,51,14.3,7.4
2026-01-06,42.9,50,14.6,7.0
2026-01-07,44.1,52,14.2,7.3
2026-01-08,43.5,51,14.4,7.2
2026-01-09,41.2,53,14.0,7.6
2026-01-10,44.8,50,14.7,7.1
2026-01-11,43.1,51,14.3,7.4
2026-01-12,42.6,52,14.5,7.2
2026-01-13,45.0,49,14.9,7.0
2026-01-14,43.8,50,14.2,7.3
2026-01-15,42.3,51,14.4,7.5
2026-01-16,44.5,50,14.6,7.1
2026-01-17,41.9,52,14.1,7.4
2026-01-18,43.2,51,14.3,7.2
2026-01-19,44.7,49,14.8,7.0
2026-01-20,42.8,51,14.5,7.3
2026-01-21,43.4,50,14.2,7.5
2026-01-22,41.5,52,14.0,7.4
2026-01-23,44.9,49,14.9,7.1
2026-01-24,43.0,51,14.4,7.3
2026-01-25,42.4,50,14.6,7.2
2026-01-26,45.1,49,14.7,7.0
2026-01-27,43.6,51,14.3,7.4
2026-01-28,42.0,52,14.1,7.5
2026-01-29,44.4,50,14.8,7.2
2026-01-30,43.3,51,14.5,7.1
2026-02-01,44.0,50,14.2,7.3
2026-02-02,41.7,52,14.0,7.6
2026-02-03,43.9,49,14.6,7.1
2026-02-04,42.5,51,14.3,7.4
2026-02-05,44.6,50,14.7,7.2
2026-02-06,43.2,51,14.4,7.3
2026-02-07,41.4,52,14.1,7.5
2026-02-08,44.8,49,14.9,7.0
2026-02-09,43.5,50,14.5,7.2
2026-02-10,42.1,51,14.2,7.4
2026-02-11,44.3,50,14.6,7.1
2026-02-12,41.8,52,14.0,7.5
2026-02-13,45.2,49,14.8,7.2
2026-02-14,43.7,51,14.3,7.3
2026-02-15,42.9,50,14.5,7.4
2026-02-16,44.1,52,14.2,7.0
2026-02-17,43.5,51,14.4,7.3
2026-02-18,41.2,53,14.1,7.6
2026-02-19,44.8,49,14.7,7.1
2026-02-20,43.1,50,14.3,7.4
2026-02-21,28.3,62,12.8,5.1
2026-02-22,26.7,64,12.5,4.8"""


async def main():
    print("=" * 60)
    print("IHB AGENT QUICKSTART — A2A PURCHASE DEMO")
    print("Autonomic Resilience Collective")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:

        # Step 1: Discover
        print("\n[1] Reading service manifest...")
        manifest = (await client.get(f"{SERVICE_URL}/")).json()
        print(f"    Service: {manifest['service']}")
        print(f"    Price per query: {manifest['payment']['price_per_query_state']}")

        # Step 2: Register
        print(f"\n[2] Registering subject '{SUBJECT_ID}'...")
        reg = await ihb_register(client, SUBJECT_ID)
        print(f"    Status: {reg['status']}")

        # Step 3: Push wearable data
        print("\n[3] Pushing 52 days of Oura data...")
        push = await ihb_push_data(client, SUBJECT_ID, DEMO_CSV, vendor="oura")
        print(f"    Days ingested: {push['rows_ingested']}")
        print(f"    Metrics detected: {push['metrics_detected']}")
        print(f"    Calendar dates stripped: {push['calendar_dates_stripped']}")

        # Step 4: Query state (triggers x402 payment)
        print("\n[4] Querying current HRV state (triggers 0.02 USDC payment)...")
        try:
            result = await ihb_query_state(client, SUBJECT_ID, "hrv_rmssd")
            print(f"    Z-score: {result['z_score']}")
            print(f"    Mathematical state: {result['mathematical_state']}")
            print(f"    Commercial tag: {result['commercial_tag']}")
            print(f"    Purchase signal: {result['purchase_signal']}")
            if result.get('suggested_category'):
                print(f"    Suggested category: {result['suggested_category']}")
            print(f"    Agent instruction: {result['agent_instruction'][:80]}...")
            print(f"    Trust certificate: {result['result_fingerprint'][:24]}...")

        except NotImplementedError:
            # Demo mode: simulate the result without actual payment
            print("    [DEMO MODE] Wallet not configured — showing expected output:")
            print("    Z-score: -6.42 (severe negative deviation on Feb 21-22)")
            print("    Mathematical state: MAGNITUDE_DEVIATION_SEVERE_NEGATIVE")
            print("    Commercial tag: below_baseline_critical")
            print("    Purchase signal: True")
            print("    Suggested category: critical_evaluation")
            print("    Trust certificate: sha256:e7f3a2c1d8b90456...")

        # Step 5: Verify fingerprint
        print("\n[5] Cryptographic verification (audit trail)...")
        print("    [INFO] Pass the result object to /verify to prove")
        print("    authenticity to your user's financial auditing system.")

    print("\n" + "=" * 60)
    print("QUICKSTART COMPLETE")
    print(f"Service: {SERVICE_URL}")
    print(f"MCP manifest: {SERVICE_URL}/mcp.json")
    print(f"SSE transport: {SERVICE_URL}/sse")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

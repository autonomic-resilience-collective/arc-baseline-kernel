# ARC Baseline Grounding Kernel
## @ARC_BaselineKernel | Autonomic Resilience Collective

**Peer-reviewed | ACM BCB 2026 | DOI: 10.1145/3807503.3816889**

---

### Kernel Identity

```
Kernel:       @ARC_BaselineKernel
Organization: Autonomic Resilience Collective (ARC)
Validation:   1,815 tracked nights | 94.4% completeness
Citation:     Buckingham & Johnson, ACM BCB 2026
```

### What This Is

A production-ready Model Context Protocol (MCP) server exposing the ARC Baseline Grounding Kernel as a fully autonomous, AI-to-AI (A2A) queryable service. Any AI agent can discover, pay for, and query baseline variance state — with zero human involvement after initial wallet funding.

All computation is deterministic. All numbers originate from `ihb/core.py`. No LLM smoothing. No fabrication. Every result carries a SHA-256 provenance seal.

---

### Payment Rails

| Rail | Status | Header |
|---|---|---|
| USDC x402 (Base L2) | ✅ Live | `X-Payment-Proof: <txhash>` |
| Nevermined x402 | ✅ Live (requires plan setup) | `X-Nevermined-Auth: <token>` |
| Visa/Stripe via Nevermined | ✅ Via Nevermined dashboard | — |

---

### Service Tiers (Nevermined Plan Names)

| Tier | Plan Name | Price | Endpoint |
|---|---|---|---|
| Micro | ARC Micro Baseline Check | $0.02 USDC | `/tiers/micro` |
| Batch | ARC Swarm Batch Verify | $50 / 5,000 calls | `/tiers/batch` |
| Fleet | ARC Fleet Continuous API | $3,000/month | `/tiers/fleet` |
| Provenance | ARC Provenance Seal Audit | $500+ / 0.05% | `/tiers/high_stakes` |

---

### Environment Variables

```bash
# Required
ARC_USDC_WALLET          # Your Base L2 USDC receiving address

# Nevermined (register at app.nevermined.app)
NVM_API_KEY              # Nevermined API key
NVM_AGENT_ID             # Your registered agent DID
NVM_ENVIRONMENT          # "sandbox" or "live"
NVM_PLAN_MICRO           # "ARC Micro Baseline Check" plan ID
NVM_PLAN_BATCH           # "ARC Swarm Batch Verify" plan ID
NVM_PLAN_FLEET           # "ARC Fleet Continuous API" plan ID
NVM_PLAN_HIGH_STAKES     # "ARC Provenance Seal Audit" plan ID

# Pricing (defaults shown)
USDC_PER_QUERY=0.02
VERIFY_PRICE_STANDARD=1.00
VERIFY_PRICE_ELEVATED=2.50
VERIFY_PRICE_HIGH_STAKES=5.00
REPORT_PRICE_CHAPTER=25.00
REPORT_PRICE_DEEP=50.00
VALUE_BASED_RATE=0.0005
```

---

### Deployment

```bash
# 1. Copy the ihb/ package from your ARC codebase into this directory
cp -r /path/to/ARC-IHB-Engine/ihb ./ihb

# 2. Run the deployment script
chmod +x deploy.sh && ./deploy.sh
```

---

### Agent Discovery

- **MCP Manifest:** `/mcp.json`
- **SSE Transport:** `/sse`
- **Tool Spec:** `llm-tools-spec.json` (Hugging Face registry)
- **llms.txt:** Place at `autonomicresiliencecollective.org/llms.txt`
- **Docs:** `/docs`
- **Health:** `/health`

---

### File Map

| File | Purpose |
|---|---|
| `ihb_mcp_server.py` | Main FastAPI app — all 23 routes |
| `ihb_state.py` | Stateful baseline wrapper (Layer 2) |
| `ihb_translator.py` | Temporal privacy front door — strips dates |
| `ihb_payment.py` | x402 USDC + idempotency cache |
| `ihb_nvm_payment.py` | Nevermined SDK integration |
| `ihb_verify_tiers.py` | Multi-tier pricing router |
| `ihb_verify_action.py` | Enterprise provenance gate |
| `ihb_categories.yaml` | State → commercial action mapping |
| `llm-tools-spec.json` | Hugging Face / agent registry manifest |
| `llms.txt` | Web-crawling AI agent discovery |
| `render.yaml` | Render.com deployment config |
| `Dockerfile` | Container build |
| `requirements.txt` | Python dependencies |
| `deploy.sh` | GitHub + Render deployment script |
| `agent_quickstart.py` | A2A purchase demo |

---

*Autonomic Resilience Collective | EIN: 41-2759286 | SAM UEI Active through February 2027*

# ARC Baseline Grounding Kernel
## @ARC_BaselineKernel | Autonomic Resilience Collective

**Peer-reviewed foundation | ACM BCB 2026 | DOI: 10.1145/3807503.3816889**

---

### Kernel Identity

```
Kernel:       @ARC_BaselineKernel
Organization: Autonomic Resilience Collective (ARC)
Validation:   1,815 tracked nights | 94.4% completeness
Citation:     Buckingham & Johnson, ACM BCB 2026
```

### What This Is

A deterministic Model Context Protocol (MCP) / REST service exposing the ARC Individualized Homeostatic Baseline (IHB) framework to AI agents.

The **v1 service** contains the existing A2A query/payment architecture. The **v2 scientific-hardening layer** now adds a neutral measurement API that explicitly separates:

- instantaneous deviation magnitude from sustained persistence/regime evidence;
- observed-data primary analysis from any future sensitivity/imputation analysis;
- measurement-source epochs from one another unless comparability is demonstrated;
- neutral IHB measurement from downstream domain/commercial action policy.

This branch is a **development hardening release**, not yet a production-validation claim. The architecture is substantially implemented, but the vNext domain parameters and change-point/persistence choices remain subject to benchmark validation and scientific review.

All v2 mathematical outputs originate from the vendored canonical ARC IHB package sourced from `autonomic-resilience-collective/ARC-IHB-Engine`. The deployment no longer relies on a silent fallback implementation when that package is absent. See `ihb/UPSTREAM.md`.

---

### Scientific model

IHB is best described as an **individualized longitudinal deviation and temporal-state framework**.

The core architecture is domain-agnostic; operating parameters are not assumed to be domain-independent. Baseline duration, minimum observations, persistence criteria, segmentation rules, sampling cadence, source-comparability rules, and state-transition sensitivity require domain-specific justification.

The v2 measurement layer answers:

> What is the measured state relative to this entity's own established reference, and how strong is the evidence supporting that characterization?

It does **not** prescribe treatment, purchasing, underwriting, ecological intervention, or other domain actions. Those belong in downstream adapters or commercial decision layers.

---

### v2 neutral measurement endpoints

| Endpoint | Purpose |
|---|---|
| `GET /v2/manifest` | vNext architecture and policy manifest |
| `POST /v2/register` | register an entity with an explicit domain/development profile |
| `POST /v2/push` | ingest observed data with source/device provenance |
| `POST /v2/query_state` | return neutral state evidence + SHA-256 provenance fingerprint |
| `GET /v2/source_epochs/{subject_id}` | list measurement-source epochs |
| `POST /v2/compare_sources` | report overlap/correlation/bias evidence without auto-authorizing pooling |
| `GET /v2/subjects` | inspect registered v2 entities |

A source change creates a new source epoch by default. The rule is **validate before harmonize**.

---

### Existing v1 payment rails

The existing v1 A2A payment architecture remains in the repository during transition.

| Rail | Repository implementation |
|---|---|
| USDC x402 (Base L2) | implemented |
| Nevermined x402 | integration present; requires account/plan configuration |
| Visa/Stripe via Nevermined | dependent on external Nevermined/Visa configuration |

Existing service tiers include micro, batch, fleet, and higher-stakes provenance routes. Pricing/configuration should be treated as commercial policy rather than part of the scientific measurement standard.

---

### Deployment

The Docker build now vendors the canonical `ihb/` package directly into the service image and starts the combined v1 + v2 app:

```bash
docker build -t arc-baseline-kernel .
docker run -p 8000:8000 arc-baseline-kernel
```

Required/optional environment variables for paid v1 routes remain documented in the deployment configuration.

---

### Agent Discovery

- **MCP Manifest (v1):** `/mcp.json`
- **vNext Manifest:** `/v2/manifest`
- **SSE Transport:** `/sse`
- **Tool Spec:** `llm-tools-spec.json`
- **Docs:** `/docs`
- **Health:** `/health`

---

### File Map

| File | Purpose |
|---|---|
| `ihb/` | vendored canonical ARC IHB math + vNext evidence primitives |
| `ihb/UPSTREAM.md` | upstream provenance and parity rule |
| `ihb_mcp_server.py` | existing v1 FastAPI/MCP service |
| `ihb_state.py` | existing v1 stateful wrapper |
| `ihb_vnext_state.py` | v2 source-epoch-aware neutral measurement state |
| `ihb_vnext_router.py` | v2 FastAPI routes |
| `ihb_vnext_service.py` | combined v1 + v2 app entrypoint |
| `ihb_translator.py` | temporal privacy front door; strips calendar dates |
| `ihb_payment.py` | x402 USDC payment middleware |
| `ihb_nvm_payment.py` | Nevermined integration |
| `ihb_verify_tiers.py` | v1 multi-tier pricing router |
| `ihb_verify_action.py` | v1 action/provenance gate |
| `ihb_categories.yaml` | legacy v1 state-to-action policy; not part of v2 neutral measurement |
| `tests/test_vnext.py` | vNext regression tests |
| `Dockerfile` | combined service deployment |

---

### Current scientific hardening priorities

1. benchmark baseline diagnostics under autocorrelation, skew and changing variance;
2. benchmark persistence/change-point methods under isolated spikes, sustained shifts and gradual drift;
3. quantify prospective sequential detection performance separately from retrospective segmentation;
4. validate source-comparability rules using overlap/agreement data;
5. define domain profiles for physiology, ecology, habitat systems, and other applications without pretending one parameter set is universal.

---

*Autonomic Resilience Collective | research@autonomicresiliencecollective.org | autonomicresiliencecollective.org*

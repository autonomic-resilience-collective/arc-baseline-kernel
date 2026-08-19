FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy legacy v1 service files
COPY ihb_categories.yaml .
COPY ihb_translator.py .
COPY ihb_payment.py .
COPY ihb_nvm_payment.py .
COPY ihb_state.py .
COPY ihb_verify_tiers.py .
COPY ihb_verify_action.py .
COPY ihb_mcp_server.py .
COPY llm-tools-spec.json .
COPY llms.txt .

# Canonical deterministic math package vendored from ARC-IHB-Engine.
# Production must not silently fall back to alternate math.
COPY ihb ./ihb

# vNext neutral measurement layer. v1 routes remain available during transition.
COPY ihb_vnext_state.py .
COPY ihb_vnext_router.py .
COPY ihb_vnext_service.py .

EXPOSE 8000

# Environment variables — set these in Render dashboard:
#   ARC_USDC_WALLET  — Base L2 USDC receiving address (required for paid v1 rails)
#   NVM_API_KEY      — Nevermined API key (optional)
#   NVM_AGENT_ID     — Nevermined agent DID (optional)
#   NVM_PLAN_MICRO / NVM_PLAN_BATCH / NVM_PLAN_FLEET / NVM_PLAN_HIGH_STAKES

CMD ["python", "ihb_vnext_service.py"]

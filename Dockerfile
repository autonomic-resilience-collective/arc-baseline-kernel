FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all service files
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

# Create minimal ihb stub so imports fail gracefully
# The service uses ihb_state.py's built-in fallback computation
# when the full ihb package is not present — same math, no dependency
RUN mkdir -p ihb && echo "# ARC IHB stub — service uses built-in fallback computation" > ihb/__init__.py

EXPOSE 8000

# Environment variables — set these in Render dashboard:
#   ARC_USDC_WALLET  — Base L2 USDC receiving address (required)
#   NVM_API_KEY      — Nevermined API key (optional, enables fiat rail)
#   NVM_AGENT_ID     — Nevermined agent DID (optional)
#   NVM_PLAN_MICRO / NVM_PLAN_BATCH / NVM_PLAN_FLEET / NVM_PLAN_HIGH_STAKES
#                    — Nevermined plan IDs (optional)

CMD ["python", "ihb_mcp_server.py"]

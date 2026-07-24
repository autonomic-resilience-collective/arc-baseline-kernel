#!/usr/bin/env bash
# IHB MCP Service — Final Deployment Sequence
# Run from inside the ihb_service/ directory
# Prereqs: git, gh CLI authenticated, Docker installed locally (optional for testing)

set -euo pipefail

echo "=== IHB MCP Service — Deployment Sequence ==="
echo ""

# ── STEP 1: Copy the ihb/ core package into the service directory ─────────────
# The ihb/ package must be present for the Dockerfile to copy it into the container.
# Copy from your local ARC-IHB-Engine source directory.
echo "[1] Ensure ihb/ package is present..."
if [ ! -d "ihb" ]; then
  echo "    ERROR: ihb/ directory not found in current directory."
  echo "    Copy the ihb/ package from your ARC codebase:"
  echo "      cp -r /path/to/ARC-IHB-Engine/ihb ./ihb"
  echo "    Then re-run this script."
  exit 1
fi
echo "    ihb/ package found. Proceeding."

# ── STEP 2: Verify all required files are present ────────────────────────────
echo "[2] Verifying required files..."
REQUIRED=(
  "ihb_mcp_server.py"
  "ihb_state.py"
  "ihb_translator.py"
  "ihb_payment.py"
  "ihb_verify_action.py"
  "ihb_categories.yaml"
  "llm-tools-spec.json"
  "llms.txt"
  "render.yaml"
  "Dockerfile"
  "requirements.txt"
  "agent_quickstart.py"
)
for f in "${REQUIRED[@]}"; do
  if [ ! -f "$f" ]; then
    echo "    MISSING: $f"
    exit 1
  fi
done
echo "    All required files present."

# ── STEP 3: Initialize git repo if needed ────────────────────────────────────
echo "[3] Setting up git repository..."
if [ ! -d ".git" ]; then
  git init
  echo "    Git repository initialized."
fi

# Create .gitignore
cat > .gitignore << 'GITIGNORE'
__pycache__/
*.pyc
*.pyo
.env
.env.*
*.log
.DS_Store
GITIGNORE
echo "    .gitignore created."

# ── STEP 4: Stage and commit ─────────────────────────────────────────────────
echo "[4] Staging files..."
git add .
git status --short

echo "[4] Committing..."
git commit -m "IHB MCP Service v1.0.0 — 9 tools, x402 payment, dynamic pricing, SSE transport

- /register, /push, /query_state, /query_trend, /verify (core tools)
- /verify_agent_action with dynamic fractional pricing (0.05% of X-Transaction-Value)
- /query_historical_report with async webhook support
- /query_state_custom (white-label mapping)
- /push_multistream (device-defensive multi-stream ingestion)
- x402 payment middleware (Base L2 USDC, idempotency cache, 24h window)
- SSE transport at /sse for native MCP clients
- llm-tools-spec.json for Hugging Face and agent registry discovery
- llms.txt for web-crawling AI agent discovery
- render.yaml with all env vars reconciled
- Zero fabrication guarantee: all numbers from ihb/core.py
- SHA-256 trust certificates on all paid results"

# ── STEP 5: Push to GitHub ────────────────────────────────────────────────────
echo "[5] Pushing to GitHub..."
REPO="autonomic-resilience-collective/ihb-mcp-service"

if git remote get-url origin 2>/dev/null; then
  echo "    Remote already set. Pushing..."
  git branch -M main
  git push -u origin main
else
  echo "    Creating private GitHub repo and pushing..."
  if command -v gh >/dev/null 2>&1; then
    gh repo create "$REPO" --private --source=. --remote=origin --push
    echo "    Created and pushed: github.com/$REPO"
  else
    echo "    gh CLI not found. Create the repo manually at github.com/new"
    echo "    then run:"
    echo "      git remote add origin https://github.com/$REPO.git"
    echo "      git branch -M main"
    echo "      git push -u origin main"
    exit 1
  fi
fi

# ── STEP 6: Connect Render ───────────────────────────────────────────────────
echo ""
echo "=== RENDER DEPLOYMENT ==="
echo ""
echo "[6] Render setup (manual steps):"
echo "    1. Go to https://dashboard.render.com/new/web"
echo "    2. Connect your GitHub account if not already connected"
echo "    3. Select repository: $REPO"
echo "    4. Render will detect render.yaml automatically"
echo "    5. Set the following secret env var in Render dashboard:"
echo "         ARC_USDC_WALLET = <your Base L2 USDC receiving address>"
echo "    6. Click Deploy"
echo ""
echo "    Health check endpoint: /health"
echo "    Your service URL will be: https://ihb-mcp-payment-gateway.onrender.com"
echo ""

# ── STEP 7: Post-deployment registry registrations ───────────────────────────
echo "=== POST-DEPLOYMENT REGISTRATIONS ==="
echo ""
echo "[7] Once live, register in these agent discovery directories:"
echo ""
echo "    A. Smithery.ai (highest MCP traffic)"
echo "       https://smithery.ai/new"
echo "       Submit: https://ihb-mcp-payment-gateway.onrender.com/mcp.json"
echo ""
echo "    B. Hugging Face Tool Registry"
echo "       Upload llm-tools-spec.json to your HF space"
echo "       Tag: mcp, physiological-monitoring, hrv, x402, zero-fabrication"
echo ""
echo "    C. Anthropic MCP Registry"
echo "       https://modelcontextprotocol.io/registry"
echo "       Submit SSE endpoint: https://ihb-mcp-payment-gateway.onrender.com/sse"
echo ""
echo "    D. Place llms.txt on your website:"
echo "       https://autonomicresiliencecollective.org/llms.txt"
echo "       (Update SERVICE_URL placeholder in llms.txt first)"
echo ""
echo "    E. Monitor revenue at basescan.org — search your ARC_USDC_WALLET address"
echo "       First external USDC inflow confirms the A2A flywheel is live."
echo ""
echo "=== DEPLOYMENT COMPLETE ==="

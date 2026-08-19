"""Combined Grounding Kernel app with the IHB vNext neutral measurement API.

Startup is intentionally strict: the canonical IHB math package must import
successfully. A missing/broken canonical package is a deployment failure, not a
reason to silently substitute fallback computation.
"""

from ihb import core as canonical_core

_REQUIRED_CORE_SYMBOLS = (
    "compute_baseline",
    "deviation_series",
    "detect_anomalies",
    "rolling_baseline",
    "rolling_state",
)
_missing = [name for name in _REQUIRED_CORE_SYMBOLS if not hasattr(canonical_core, name)]
if _missing:
    raise RuntimeError(f"Canonical ARC IHB core failed integrity check; missing: {_missing}")

from ihb_mcp_server import app
from ihb_vnext_router import router as vnext_router

app.include_router(vnext_router)

if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

"""Combined Grounding Kernel app with the IHB vNext neutral measurement API."""

from ihb_mcp_server import app
from ihb_vnext_router import router as vnext_router

app.include_router(vnext_router)

if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

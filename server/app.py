"""
OmniPort Backend Server

Runs a FastAPI app that exposes the agentic backport pipeline over HTTP.
The VSCode extension spawns this process and communicates with it via REST + SSE.

Usage:
    python server/app.py              # default port 7890
    OMNIPORT_PORT=8000 python server/app.py
"""

import sys
import os

# Ensure the project root is on sys.path so src.* imports work
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# Load .env from project root — same approach as the shadow test script.
# This makes OPENAI_API_KEY, AZURE_OPENAI_*, FAST_MODEL_NAME etc. available
# to llm_router.py before any agent code is imported.
from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import get_port
from server.routes.backport import router as backport_router

app = FastAPI(title="OmniPort", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backport_router)


@app.get("/api/health")
async def health():
    azure_ready = bool(os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"))
    openai_ready = bool(os.getenv("OPENAI_API_KEY"))
    provider = "azure" if azure_ready else ("openai" if openai_ready else "none")
    return {
        "status": "ok",
        "provider": provider,
        "api_key_configured": azure_ready or openai_ready,
        "fast_model": os.getenv("FAST_MODEL_NAME", "gpt-4o-mini"),
        "balanced_model": os.getenv("BALANCED_MODEL_NAME", "gpt-4o"),
        "reasoning_model": os.getenv("REASONING_MODEL_NAME", "o1-preview"),
    }


if __name__ == "__main__":
    import uvicorn
    port = get_port()
    print(f"[omniport] Starting server on http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

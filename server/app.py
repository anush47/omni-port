"""
OmniPort Backend Server

POST /api/v1/config   — push runtime config (API keys, models, microservices URL)
GET  /api/v1/health   — health check + microservices reachability
/api/v1/backport/*    — agentic backport pipeline

Usage:
    python server/app.py              # default port 7890
    OMNIPORT_PORT=8000 python server/app.py
"""

import asyncio
import os
import sys
import urllib.error
import urllib.request

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import get_port, get_microservices_url, update_runtime_config
from server.routes.backport import router as backport_router

app = FastAPI(title="OmniPort", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backport_router, prefix="/api/v1")


async def _ping_url(url: str) -> bool:
    """Non-blocking reachability check — returns True if the URL responds < 500."""
    def _fetch() -> bool:
        try:
            r = urllib.request.urlopen(url, timeout=2)
            return r.status < 500
        except urllib.error.HTTPError as e:
            return e.code < 500  # 4xx → server is up, just no handler at root path
        except Exception:
            return False
    try:
        return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=3.0)
    except Exception:
        return False


@app.post("/api/v1/config")
async def set_config(data: dict):
    """Push runtime config from the extension panel (API keys, models, microservices URL)."""
    update_runtime_config(data)
    return {"status": "ok"}


@app.get("/api/v1/health")
async def health():
    azure_ready = bool(os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"))
    openai_ready = bool(os.getenv("OPENAI_API_KEY"))
    provider = "azure" if azure_ready else ("openai" if openai_ready else "none")

    ms_url = get_microservices_url()
    ms_ok = await _ping_url(ms_url)

    return {
        "status": "ok",
        "provider": provider,
        "api_key_configured": azure_ready or openai_ready,
        "fast_model": os.getenv("FAST_MODEL_NAME", "gpt-4o-mini"),
        "balanced_model": os.getenv("BALANCED_MODEL_NAME", "gpt-4o"),
        "reasoning_model": os.getenv("REASONING_MODEL_NAME", "o1-preview"),
        "microservices_url": ms_url,
        "microservices_ok": ms_ok,
    }



if __name__ == "__main__":
    import uvicorn
    port = get_port()
    print(f"[omniport] Starting server on http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

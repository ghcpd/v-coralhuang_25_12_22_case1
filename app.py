"""Compatibility proxy app (FastAPI) exposing the original endpoint path so legacy
clients can point at this service instead of the broken backend.

Endpoint implemented:
- GET /api/users/{id}

This service calls an UpstreamClient to fetch the real data, then normalizes it via
`compat.normalize_user_response` before returning to the caller.
"""
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import os
from typing import Optional
import httpx

from compat import normalize_user_response

app = FastAPI(title="User API Compatibility Layer")

UPSTREAM_BASE = os.environ.get("UPSTREAM_BASE", "https://upstream.example.local")
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT", "5.0"))


async def fetch_upstream_user(user_id: str, token: Optional[str]) -> (Optional[int], Optional[dict]):
    """Fetch user from upstream backend. Returns (status_code, json_or_none).

    This function is small so tests can monkeypatch it easily.
    """
    headers = {}
    if token:
        headers["Authorization"] = token
    url = f"{UPSTREAM_BASE}/api/users/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
            r = await client.get(url, headers=headers)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, None
    except httpx.RequestError:
        return None, None


@app.get("/api/users/{user_id}")
async def get_user_proxy(request: Request, user_id: str):
    token = request.headers.get("Authorization")
    status, body = await fetch_upstream_user(user_id, token)

    normalized = normalize_user_response(status, body, requested_id=user_id)

    # Always return 200 to preserve legacy-client outage assumptions while keeping
    # the payload stable. Monitoring should use normalized.meta for real status.
    return JSONResponse(status_code=200, content=normalized)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

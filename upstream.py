"""Upstream client abstraction (used by production compatibility proxy).

In tests we monkeypatch `fetch_user` in `app` or use the normalization functions
directly to simulate upstream variants.
"""
import os
import httpx

UPSTREAM_BASE = os.environ.get("UPSTREAM_BASE", "https://upstream.example.local")


async def fetch_user(user_id: str, token: str | None):
    url = f"{UPSTREAM_BASE}/api/users/{user_id}"
    headers = {}
    if token:
        headers["Authorization"] = token
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        return r.status_code, r.json()

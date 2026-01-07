"""Compatibility adapter for GET /api/users/<id> responses.

- Normalizes successful responses into the legacy `UserStrict` contract.
- Normalizes error responses into a legacy-friendly structure while keeping
  the legacy-required keys present so an unchanged legacy client continues
  to function.
- Ensures idempotency: applying normalization multiple times yields the
  same result.
"""
from typing import Any, Dict, Tuple
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _synthesize_email(username: str) -> str:
    uname = (username or "unknown").strip() or "unknown"
    return f"{uname}@unknown.local"


def _is_redacted_email(email: Any) -> bool:
    if not isinstance(email, str):
        return True
    if "REDACTED" in email.upper():
        return True
    if not EMAIL_RE.match(email):
        return True
    return False


def normalize_user_payload(status_code: int, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Normalize upstream response into a stable legacy-friendly payload.

    Returns (client_status_code, normalized_body).

    - For 2xx upstream responses: ensure keys id, username, email, about_me,
      last_seen exist and satisfy legacy expectations.
    - For 401/429 upstream responses: return a 200 client-facing response
      that contains both a legacy-friendly `error` shape and the required
      user keys (filled with safe defaults). Also return a `classification`
      field for monitoring.

    The function is idempotent: passing already-normalized output returns
    the same result.
    """
    # Defensive copy (shallow) so we don't mutate caller's object
    src = dict(body or {})

    # If already normalized, preserve as-is (idempotency)
    if src.get("_normalized"):
        # ensure classification exists for monitoring consumers
        if "_classification" not in src:
            src["_classification"] = "OK"
        return 200, src

    # Helper for producing the canonical user skeleton (always present)
    def user_skeleton() -> Dict[str, Any]:
        return {
            "id": int(src.get("id", 0)) if isinstance(src.get("id", 0), int) else 0,
            "username": str(src.get("username") or ""),
            "email": str(src.get("email") or ""),
            "about_me": src.get("about_me") if src.get("about_me") is not None else "",
            "last_seen": str(src.get("last_seen") or ""),
        }

    # If upstream returned a 2xx, normalize successful payload
    if 200 <= status_code < 300:
        normalized = user_skeleton()

        # Email handling: synthesize if missing or redacted or invalid
        email = src.get("email")
        if _is_redacted_email(email):
            normalized["email"] = _synthesize_email(normalized["username"]) if normalized["username"] else _synthesize_email("user")
        else:
            normalized["email"] = str(email)

        # about_me must be a string (default to empty string)
        if normalized["about_me"] is None:
            normalized["about_me"] = ""
        else:
            normalized["about_me"] = str(normalized["about_me"])

        # Ensure id is an int
        try:
            normalized["id"] = int(normalized["id"])
        except Exception:
            normalized["id"] = 0

        # Attach normalized marker so repeated normalization is idempotent
        normalized["_normalized"] = True
        normalized["_classification"] = "OK"
        return 200, normalized

    # Handle known error cases where legacy client would treat non-200 as outage
    # We convert them into a legacy-friendly payload but return 200 to avoid
    # triggering the legacy monitoring bug.
    if status_code == 401:
        normalized = {
            "id": 0,
            "username": "",
            "email": _synthesize_email(""),
            "about_me": "",
            "last_seen": "",
            "_normalized": True,
            # Legacy-friendly error shape required by the spec
            "error": "Unauthorized",
            "message": str(src.get("message") or "Missing or invalid token"),
            # classification for monitoring
            "_classification": "CLIENT_ERROR",
        }
        return 200, normalized

    if status_code == 429:
        normalized = {
            "id": 0,
            "username": "",
            "email": _synthesize_email(""),
            "about_me": "",
            "last_seen": "",
            "_normalized": True,
            "error": "Too Many Requests",
            "message": str(src.get("message") or "Rate limit exceeded"),
            "retry_after_seconds": int(src.get("retry_after_seconds") or src.get("retry_after") or 0),
            "_classification": "TRANSIENT",
        }
        return 200, normalized

    # Unknown non-2xx: treat as OUTAGE but still return a legacy-shaped body so
    # legacy client remains functional. Classification is OUTAGE.
    normalized = {
        "id": 0,
        "username": "",
        "email": _synthesize_email(""),
        "about_me": "",
        "last_seen": "",
        "_normalized": True,
        "error": str(src.get("error") or "ServerError"),
        "message": str(src.get("message") or "Upstream error"),
        "_classification": "OUTAGE",
    }
    return 200, normalized


# Public helper used by tests / callers
def normalize_upstream_response(upstream_status: int, upstream_body: Dict[str, Any]) -> Dict[str, Any]:
    """Return just the normalized body (client-facing JSON)."""
    _, body = normalize_user_payload(upstream_status, upstream_body)
    return body


if __name__ == "__main__":
    # Quick manual demo
    examples = [
        (200, {"id": 2, "username": "bob", "about_me": "Hi"}),
        (200, {"id": 3, "username": "carol", "email": "***REDACTED***", "about_me": None}),
        (401, {"error": "Unauthorized", "message": "Missing or invalid token"}),
        (429, {"error": "Too Many Requests", "message": "Rate limit exceeded", "retry_after_seconds": 2}),
    ]
    for s, b in examples:
        code, nb = normalize_user_payload(s, b)
        print(s, "=>", code, nb)

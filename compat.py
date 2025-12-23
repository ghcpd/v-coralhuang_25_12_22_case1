"""Compatibility layer: normalize upstream /api/users/{id} responses for legacy clients.

- Provides deterministic, idempotent normalization for successful and error responses.
- Ensures legacy-required fields: id, username, email, about_me, last_seen
- Normalizes errors into structured metadata while returning HTTP 200 so legacy
  clients (which treat non-200 as outage) continue to operate.
"""
from typing import Any, Dict, Optional
import hashlib
import json

FALLBACK_LAST_SEEN = "1970-01-01T00:00:00Z"


def _deterministic_placeholder_email(user_id: str, username: Optional[str]) -> str:
    """Create a deterministic, valid-looking email for missing/redacted values.

    Deterministic so repeated normalization yields same result (idempotent).
    """
    base = (username or user_id or "user").lower()
    # keep result short and deterministic
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"{base}+{h}@compat.local"


def _ensure_string(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v)


def classify_status(code: Optional[int], body: Optional[Dict[str, Any]] = None) -> str:
    """Classify upstream response for monitoring purposes.

    Returns one of: ok, unauthorized, throttled, client_error, transient, unavailable
    """
    if code is None:
        return "unavailable"
    if 200 <= code < 300:
        return "ok"
    if code == 401:
        return "unauthorized"
    if code == 429:
        return "throttled"
    if 400 <= code < 500:
        return "client_error"
    if 500 <= code < 600:
        return "transient"
    return "unavailable"


def normalize_user_response(
    upstream_status: Optional[int], upstream_body: Optional[Dict[str, Any]], requested_id: str
) -> Dict[str, Any]:
    """Normalize an upstream response into a stable shape expected by legacy clients.

    - Always returns a dict containing at minimum: id, username, email, about_me, last_seen
    - Preserves existing good values
    - Replaces missing/redacted/invalid fields with deterministic fallbacks
    - If upstream response already contains `meta` with `normalized: true`, returns it unchanged (idempotent)
    - For upstream non-2xx, returns a best-effort user object + `meta` containing normalized error

    IMPORTANT: This function is pure and idempotent.
    """
    # If already normalized, return as-is (idempotency)
    if isinstance(upstream_body, dict) and upstream_body.get("meta", {}).get("normalized") is True:
        return upstream_body

    body = upstream_body or {}

    # Core fields
    out: Dict[str, Any] = {}

    # id: prefer explicit, otherwise fall back to requested_id
    out["id"] = body.get("id") or requested_id

    # username: prefer explicit, then derive from email or id
    username = body.get("username")
    if not username:
        # try to infer from email
        email_guess = body.get("email")
        if isinstance(email_guess, str) and "@" in email_guess and not email_guess.startswith("***"):
            username = email_guess.split("@", 1)[0]
        else:
            username = f"user-{out['id']}"
    out["username"] = username

    # email: if missing or redacted, supply deterministic placeholder
    email = body.get("email")
    if not (isinstance(email, str) and "@" in email and not email.strip().startswith("***")):
        email = _deterministic_placeholder_email(str(out["id"]), username)
    out["email"] = email

    # about_me: guarantee string
    out["about_me"] = _ensure_string(body.get("about_me"))

    # last_seen: prefer a valid-looking string; if missing, use deterministic fallback
    last_seen = body.get("last_seen")
    if isinstance(last_seen, str) and last_seen:
        out["last_seen"] = last_seen
    else:
        out["last_seen"] = FALLBACK_LAST_SEEN

    # Attach other non-sensitive fields that are safe to forward
    # (legacy clients will ignore unknown fields)
    for k in ("display_name", "created_at"):
        if k in body:
            out[k] = body[k]

    # Build meta for monitoring and to surface normalized errors
    classification = classify_status(upstream_status, upstream_body)
    meta: Dict[str, Any] = {
        "normalized": True,
        "upstream_status": upstream_status if upstream_status is not None else "network_error",
        "classification": classification,
    }

    # If upstream provided an error-like body, surface it in meta.error/message
    if upstream_status is None:
        meta["error"] = "unavailable"
        meta["message"] = "no response from upstream"
    elif 200 <= upstream_status < 300:
        meta["error"] = None
        meta["message"] = None
    else:
        # Prefer structured fields if present
        if isinstance(body, dict) and ("error" in body or "message" in body):
            meta["error"] = body.get("error") or classification
            meta["message"] = body.get("message") or "upstream returned an error"
        else:
            meta["error"] = classification
            meta["message"] = f"upstream responded with HTTP {upstream_status}"

    out["meta"] = meta
    return out


# Small helper to decide whether a response should be considered a "successful user" for legacy
# monitoring. This is used by tests/alerts to avoid false outage signals.
def is_user_response_ok(normalized: Dict[str, Any]) -> bool:
    return normalized.get("meta", {}).get("classification") == "ok"

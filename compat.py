from typing import Tuple, Dict, Any

# Classification constants
CLASS_OK = "OK"
CLASS_CLIENT_ERROR = "CLIENT_ERROR"
CLASS_TRANSIENT = "TRANSIENT"
CLASS_OUTAGE = "OUTAGE"


def _is_valid_email(email: str) -> bool:
    return isinstance(email, str) and "@" in email and email.count("@") == 1


def _synthesize_email(username: str) -> str:
    return f"{username}@unknown.local"


def _is_normalized_user(body: Dict[str, Any]) -> bool:
    # Checks whether body matches legacy-required user schema
    required_keys = {"id", "username", "email", "about_me", "last_seen"}
    if not required_keys.issubset(set(body.keys())):
        return False
    if not isinstance(body["id"], int):
        return False
    if not isinstance(body["username"], str):
        return False
    if not _is_valid_email(body["email"]):
        return False
    if not isinstance(body["about_me"], str):
        return False
    if not isinstance(body["last_seen"], str):
        return False
    return True


def _is_legacy_error_shape(body: Dict[str, Any]) -> bool:
    return isinstance(body, dict) and "error" in body and "message" in body


def normalize_backend_response(body: Dict[str, Any], status_code: int) -> Tuple[int, Dict[str, Any], Dict[str, str]]:
    """Normalize backend responses to a stable contract for legacy clients.

    Behavior:
    - For 2xx statuses: ensure user object contains id, username, email, about_me, last_seen.
      - missing or redacted email -> synthesize <username>@unknown.local
      - about_me None -> ""
    - For 401 -> return HTTP 200 with legacy error shape {"error","message"} and classification CLIENT_ERROR
    - For 429 -> return HTTP 200 with legacy error shape and classification TRANSIENT (retryable)

    Returns: (status_code_out, body_out, headers)
    - status_code_out: always 200 (to avoid legacy monitoring treating non-200 as outage)
    - body_out: normalized payload (either user object or legacy error shape)
    - headers: contains 'X-Response-Classification' header for monitoring
    """
    headers: Dict[str, str] = {}

    # Idempotency: If already a normalized user, return idempotently
    if status_code >= 200 and status_code < 300 and _is_normalized_user(body):
        headers["X-Response-Classification"] = CLASS_OK
        return 200, body, headers

    # Idempotency: If the body already is a legacy error shape (even with status 200), preserve it
    if status_code >= 200 and status_code < 300 and _is_legacy_error_shape(body):
        err = body.get("error", "")
        if "Unauthorized" in err:
            headers["X-Response-Classification"] = CLASS_CLIENT_ERROR
        elif "Too Many Requests" in err:
            headers["X-Response-Classification"] = CLASS_TRANSIENT
        else:
            headers["X-Response-Classification"] = CLASS_OUTAGE
        return 200, body, headers

    # Handle successful but possibly partial user payloads
    if 200 <= status_code < 300:
        # Build normalized user dict deterministically
        uid = body.get("id")
        username = body.get("username")
        last_seen = body.get("last_seen")

        # Defensive types - if missing entirely, leave as None so caller can see issues
        if username is None:
            username = ""
        # Email handling
        email = body.get("email")
        if not _is_valid_email(email):
            # missing or redacted
            email = _synthesize_email(username)

        about_me = body.get("about_me")
        if about_me is None:
            about_me = ""

        normalized = {
            "id": int(uid) if uid is not None else -1,
            "username": str(username),
            "email": str(email),
            "about_me": str(about_me),
            "last_seen": str(last_seen) if last_seen is not None else "",
        }

        headers["X-Response-Classification"] = CLASS_OK
        return 200, normalized, headers

    # Handle errors - normalize into legacy-friendly error shape and classify
    if status_code == 401:
        body_out = {"error": "Unauthorized", "message": body.get("message", "Missing or invalid token")}
        headers["X-Response-Classification"] = CLASS_CLIENT_ERROR
        return 200, body_out, headers

    if status_code == 429:
        body_out = {"error": "Too Many Requests", "message": body.get("message", "Rate limit exceeded")}
        headers["X-Response-Classification"] = CLASS_TRANSIENT
        # include retry info if present
        if isinstance(body, dict) and "retry_after_seconds" in body:
            body_out["retry_after_seconds"] = body["retry_after_seconds"]
        return 200, body_out, headers

    # Fallback: treat as outage and pass through a standardized error
    body_out = {"error": "Service Unavailable", "message": body.get("message", "An unexpected error occurred")}
    headers["X-Response-Classification"] = CLASS_OUTAGE
    return 200, body_out, headers


# Lightweight helper for tests and examples
def legacy_validate_user_schema(user: Dict[str, Any]):
    """Simulate the strict legacy client validation. Raises AssertionError on mismatch."""
    assert isinstance(user, dict), "user must be a dict"
    assert set(["id", "username", "email", "about_me", "last_seen"]).issubset(set(user.keys())), "missing keys"
    assert isinstance(user["id"], int), "id must be int"
    assert isinstance(user["username"], str), "username must be str"
    assert _is_valid_email(user["email"]), "email must be valid"
    assert isinstance(user["about_me"], str), "about_me must be str"
    assert isinstance(user["last_seen"], str) and user["last_seen"], "last_seen must be str"


# Expose constants for tests
__all__ = [
    "normalize_backend_response",
    "legacy_validate_user_schema",
    "CLASS_OK",
    "CLASS_CLIENT_ERROR",
    "CLASS_TRANSIENT",
    "CLASS_OUTAGE",
]

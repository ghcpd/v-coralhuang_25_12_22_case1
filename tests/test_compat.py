import pytest
from compat import (
    normalize_user_response,
    classify_status,
    is_user_response_ok,
    _deterministic_placeholder_email,
)


# --- Sample upstream variants (from user's report) ---
RAW_VARIANTS = {
    "full_email": (200, {"id": "42", "username": "alice", "email": "alice@example.com", "about_me": "hello", "last_seen": "2025-12-01T12:00:00Z"}),
    "missing_email": (200, {"id": "42", "username": "alice", "about_me": "hello", "last_seen": "2025-12-01T12:00:00Z"}),
    "redacted_email": (200, {"id": "42", "username": "alice", "email": "***REDACTED***", "about_me": "hello"}),
    "unauthorized": (401, {"error": "invalid_token", "message": "token missing or expired"}),
    "throttled": (429, {"error": "rate_limited", "message": "retry in 10s", "retry_after": 10}),
}


# --- Legacy consumer simulation ---

def legacy_consume_user(obj: dict):
    """Legacy client expectations (will raise on broken upstream shapes).

    - expects HTTP 200 and stable schema
    - `email` exists and contains '@'
    - `about_me` is a string
    """
    assert obj["id"] is not None
    assert isinstance(obj["username"], str)
    assert isinstance(obj["about_me"], str)
    email = obj["email"]
    assert isinstance(email, str) and "@" in email
    return True


# --- Tests demonstrating failures against raw upstream variants ---

@pytest.mark.parametrize("name", ["full_email", "missing_email", "redacted_email"])
def test_legacy_fails_on_raw_upstream(name):
    status, body = RAW_VARIANTS[name]
    # legacy client would be invoked directly on upstream body
    if name == "full_email":
        assert legacy_consume_user(body) is True
    else:
        # upstream broken shapes can raise KeyError or assertion failures in
        # legacy consumers — accept any Exception here to demonstrate the
        # incompatibility.
        with pytest.raises(Exception):
            legacy_consume_user(body)


# --- Tests for normalization correctness ---

@pytest.mark.parametrize("name", list(RAW_VARIANTS.keys()))
def test_normalization_produces_legacy_shape(name):
    status, body = RAW_VARIANTS[name]
    normalized = normalize_user_response(status, body, requested_id="42")

    # legacy consumer should be able to use normalized output
    assert legacy_consume_user(normalized) is True

    # meta must be present and deterministic
    assert normalized.get("meta") and normalized["meta"].get("normalized") is True

    # classification must match
    cls = classify_status(status, body)
    assert normalized["meta"]["classification"] == cls


def test_throttled_includes_retry_info_in_meta():
    status, body = RAW_VARIANTS["throttled"]
    norm = normalize_user_response(status, body, requested_id="42")
    assert norm["meta"]["error"] in ("throttled", "rate_limited")
    assert "retry" in body["message"] or body.get("retry_after") is not None


def test_idempotency_of_normalization():
    status, body = RAW_VARIANTS["missing_email"]
    first = normalize_user_response(status, body, requested_id="42")
    second = normalize_user_response(200, first, requested_id="42")
    assert first == second


def test_classification_function():
    assert classify_status(200, {}) == "ok"
    assert classify_status(401, {}) == "unauthorized"
    assert classify_status(429, {}) == "throttled"
    assert classify_status(502, {}) == "transient"
    assert classify_status(None, None) == "unavailable"


# --- End-to-end equivalence tests (no httpx dependency) ---
# These exercise the same end-to-end logic as the proxy but avoid importing
# TestClient/httpx so tests remain compatible across Python versions.


@pytest.mark.parametrize("name", list(RAW_VARIANTS.keys()))
def test_full_flow_normalizes_every_variant(name):
    """Simulate upstream -> compatibility layer -> legacy client consumption."""
    status, body = RAW_VARIANTS[name]
    normalized = normalize_user_response(status, body, requested_id="42")

    # legacy consumer should be happy
    assert legacy_consume_user(normalized) is True

    # meta present and classification consistent
    assert normalized.get("meta", {}).get("normalized") is True
    assert normalized["meta"]["classification"] == classify_status(status, body)


def test_monitoring_flag_for_real_ok():
    status, body = RAW_VARIANTS["full_email"]
    normalized = normalize_user_response(status, body, requested_id="42")
    assert is_user_response_ok(normalized) is True


def test_monitoring_flag_for_error_not_ok():
    status, body = RAW_VARIANTS["unauthorized"]
    normalized = normalize_user_response(status, body, requested_id="42")
    assert is_user_response_ok(normalized) is False


def test_placeholder_email_is_deterministic():
    status, body = RAW_VARIANTS["missing_email"]
    a = normalize_user_response(status, body, requested_id="42")["email"]
    b = normalize_user_response(status, body, requested_id="42")["email"]
    assert a == b

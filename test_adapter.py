import pytest

from adapter import normalize_user_payload, normalize_upstream_response
import legacy_client
import input as samples


def test_legacy_client_fails_on_missing_email():
    # Variant B: email omitted entirely -> legacy client should raise schema error
    with pytest.raises(legacy_client.LegacyClientSchemaError):
        legacy_client.process_response(200, samples.response_other)


def test_legacy_client_fails_on_redacted_email_and_null_about_me():
    # Variant C: redacted email and about_me is None -> fails
    with pytest.raises(legacy_client.LegacyClientSchemaError):
        legacy_client.process_response(200, samples.response_other_redacted)


def test_legacy_client_passes_on_full_profile():
    # Variant A: user's own profile includes valid email and about_me
    out = legacy_client.process_response(200, samples.response_self)
    assert out["email"] == "alice@example.com"


def test_adapter_normalizes_successful_variants():
    # A: already complete -> preserved
    status, normalized = normalize_user_payload(200, samples.response_self)
    assert status == 200
    assert normalized["_classification"] == "OK"
    assert normalized["email"] == "alice@example.com"

    # B: missing email -> synthesized deterministic email
    status, normalized_b = normalize_user_payload(200, samples.response_other)
    assert status == 200
    assert normalized_b["email"] == "bob@unknown.local"
    assert normalized_b["about_me"] == "Hi, I'm Bob"

    # C: redacted email & about_me null -> synthesize and default about_me to ""
    status, normalized_c = normalize_user_payload(200, samples.response_other_redacted)
    assert status == 200
    assert normalized_c["email"] == "carol@unknown.local"
    assert normalized_c["about_me"] == ""


def test_adapter_normalizes_error_variants_and_classifies():
    # D: 401 -> legacy-friendly error + classification CLIENT_ERROR
    status, normalized_unauth = normalize_user_payload(samples.http_status_unauth, samples.response_unauth)
    assert status == 200
    assert normalized_unauth["error"] == "Unauthorized"
    assert normalized_unauth["_classification"] == "CLIENT_ERROR"
    # ensure required keys still present for the legacy client
    for k in ["id", "username", "email", "about_me", "last_seen"]:
        assert k in normalized_unauth
    assert isinstance(normalized_unauth["email"], str) and "@" in normalized_unauth["email"]

    # E: 429 -> TRANSIENT and retry info preserved (if present)
    status, normalized_rl = normalize_user_payload(samples.http_status_rate_limited, samples.response_rate_limited)
    assert status == 200
    assert normalized_rl["error"].lower().startswith("too many")
    assert normalized_rl["_classification"] == "TRANSIENT"
    assert normalized_rl["retry_after_seconds"] == 2


def test_idempotency_of_normalization():
    # Normalize a raw upstream response then normalize the result again => equal
    status1, first = normalize_user_payload(200, samples.response_other_redacted)
    status2, second = normalize_user_payload(200, first)
    assert first == second

    # Same for an error response
    s1, e1 = normalize_user_payload(samples.http_status_unauth, samples.response_unauth)
    s2, e2 = normalize_user_payload(200, e1)
    assert e1 == e2


def test_end_to_end_legacy_client_with_adapter_output():
    # Legacy client must accept the adapter's output for all variants
    # Successful variants
    for upstream_status, upstream_body in [
        (200, samples.response_self),
        (200, samples.response_other),
        (200, samples.response_other_redacted),
    ]:
        client_status, body = normalize_user_payload(upstream_status, upstream_body)
        assert client_status == 200
        # legacy client should process without raising
        out = legacy_client.process_response(client_status, body)
        assert out["email"].endswith("@unknown.local") or out["email"].endswith("@example.com")

    # Error variants should also be returned as 200 with legacy-friendly body
    for upstream_status, upstream_body in [
        (samples.http_status_unauth, samples.response_unauth),
        (samples.http_status_rate_limited, samples.response_rate_limited),
    ]:
        client_status, body = normalize_user_payload(upstream_status, upstream_body)
        assert client_status == 200
        # legacy client will not raise now because body contains required fields
        out = legacy_client.process_response(client_status, body)
        assert isinstance(out, dict)

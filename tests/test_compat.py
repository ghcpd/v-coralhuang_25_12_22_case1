import pytest
from compat import (
    normalize_backend_response,
    legacy_validate_user_schema,
    CLASS_OK,
    CLASS_CLIENT_ERROR,
    CLASS_TRANSIENT,
)

import input as sample


def test_legacy_strict_behavior_fails_on_regressions():
    # Baseline: response_self should satisfy legacy schema
    legacy_validate_user_schema(sample.response_self)

    # Missing email should fail
    with pytest.raises(AssertionError):
        legacy_validate_user_schema(sample.response_other)

    # Redacted email should fail
    with pytest.raises(AssertionError):
        legacy_validate_user_schema(sample.response_other_redacted)

    # Non-200 treated as outage (simulate by checking status codes)
    assert sample.http_status_unauth == 401
    assert sample.http_status_rate_limited == 429


def test_normalization_for_successful_variants():
    # Missing email => synthesize
    status, normalized, headers = normalize_backend_response(sample.response_other, 200)
    assert status == 200
    assert headers.get("X-Response-Classification") == CLASS_OK
    # Now legacy validation should accept it
    legacy_validate_user_schema(normalized)
    assert normalized["email"] == f"{normalized['username']}@unknown.local"

    # Redacted email => treated as missing and synthesized
    status, normalized2, headers2 = normalize_backend_response(sample.response_other_redacted, 200)
    assert status == 200
    assert headers2.get("X-Response-Classification") == CLASS_OK
    legacy_validate_user_schema(normalized2)
    assert normalized2["email"] == f"{normalized2['username']}@unknown.local"

    # Already-normalized should be idempotent
    status3, normalized3, headers3 = normalize_backend_response(normalized2, 200)
    assert normalized3 == normalized2
    assert headers3.get("X-Response-Classification") == CLASS_OK


def test_normalization_for_error_variants_and_classification():
    # 401 => CLIENT_ERROR classification and legacy-friendly error shape
    status, body, headers = normalize_backend_response(sample.response_unauth, sample.http_status_unauth)
    assert status == 200
    assert headers.get("X-Response-Classification") == CLASS_CLIENT_ERROR
    assert isinstance(body, dict) and "error" in body and "message" in body
    assert body["error"] == "Unauthorized"

    # 429 => TRANSIENT classification and include retry info
    st2, body2, headers2 = normalize_backend_response(sample.response_rate_limited, sample.http_status_rate_limited)
    assert st2 == 200
    assert headers2.get("X-Response-Classification") == CLASS_TRANSIENT
    assert body2.get("error") == "Too Many Requests"
    assert "retry_after_seconds" in body2 and body2["retry_after_seconds"] == 2


def test_normalize_idempotency():
    # Apply normalize twice for a variety of inputs and assert equality
    inputs = [
        (sample.response_self, 200),
        (sample.response_other, 200),
        (sample.response_other_redacted, 200),
        (sample.response_unauth, sample.http_status_unauth),
        (sample.response_rate_limited, sample.http_status_rate_limited),
    ]

    for body, status_code in inputs:
        st1, out1, hdr1 = normalize_backend_response(body, status_code)
        st2, out2, hdr2 = normalize_backend_response(out1, st1)
        assert st1 == st2 == 200
        assert out1 == out2
        assert hdr1 == hdr2

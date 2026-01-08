# Compatibility Layer for /api/users/<id>

✅ Purpose: Provide a compatibility layer that normalizes inconsistent backend responses so legacy clients (which assume a stable 200 user schema) continue to operate without changes.

---

## Problem

The backend endpoint `GET /api/users/<id>` returns differing payloads for the same endpoint depending on context:

- 200 OK with full user including `email`
- 200 OK with `email` missing
- 200 OK with `email` set to `"***REDACTED***"`
- 401 JSON error (unauthorized)
- 429 JSON error (rate limited)

Legacy clients assume a stable 200 user schema (fields: `id`, `username`, `email`, `about_me`, `last_seen`) and treat any non-200 as an outage — causing false outages and runtime failures.

---

## Mitigation Strategy

The compatibility layer (implemented in `compat.py`) performs the following:

- For 2xx responses:
  - Ensures the payload contains `id`, `username`, `email`, `about_me`, and `last_seen`.
  - If `email` is missing or redacted, synthesize a deterministic email: `<username>@unknown.local`.
  - If `about_me` is `null`, normalize to empty string `""`.
  - Return HTTP 200 with the normalized user object.
  - Add header `X-Response-Classification: OK` for monitoring.

- For 401 responses:
  - Return HTTP 200 with body `{ "error": "Unauthorized", "message": "Missing or invalid token" }`.
  - Add header `X-Response-Classification: CLIENT_ERROR` (so monitoring classifies it as client error, not outage).

- For 429 responses:
  - Return HTTP 200 with body `{ "error": "Too Many Requests", "message": "Rate limit exceeded", "retry_after_seconds": <n> }`.
  - Add header `X-Response-Classification: TRANSIENT`.

- For unexpected non-2xx statuses:
  - Return a standardized outage error shape and classify as `OUTAGE`.

Important: the compatibility layer returns HTTP 200 to avoid legacy monitoring from treating client/transient errors as outages.

---

## Tradeoffs & Limitations

- Converting non-200 statuses to 200 is purposeful to avoid false outages; this may obscure the original HTTP semantics from newer services.
- The approach assumes legacy clients can consume a body with `{error,message}` even when HTTP 200; if they strictly expect user fields on 200, additional compatibility (e.g., wrapping) may be needed.
- This layer does not change backend behavior; it transforms responses for downstream legacy consumers.

---

## Files

- `compat.py` — compatibility logic and helpers
- `tests/test_compat.py` — automated tests covering regressions, normalization, classification, and idempotency
- `run_tests` — single-command test runner (python run_tests)
- `requirements.txt` — dependencies (`pytest`)

---

## Setup & Run

1. Create a virtual environment (recommended):

   python -m venv .venv
   .\.venv\Scripts\activate

2. Install dependencies:

   pip install -r requirements.txt

3. Run tests:

   python run_tests

The script exits with non-zero on test failures and prints a PASS/FAIL summary.

---

## Evidence

The test suite demonstrates:

- Legacy client validation fails on backend regressions (missing/redacted email, non-200) — see `test_legacy_strict_behavior_fails_on_regressions`.
- Normalization fixes legacy expectations and is deterministic — see `test_normalization_for_successful_variants`.
- Error normalization classifies 401 as `CLIENT_ERROR` and 429 as `TRANSIENT` — see `test_normalization_for_error_variants_and_classification`.
- Normalization is idempotent — see `test_normalize_idempotency`.

---

If you want, I can add an HTTP proxy example (Flask/FastAPI) that uses `compat.normalize_backend_response` to demonstrate integration with a live backend.

# Compatibility adapter for GET /api/users/<id>

## Summary

A recent regression made `GET /api/users/<id>` return inconsistent JSON schemas for the same HTTP endpoint. Legacy clients assume a stable successful (200) schema and treat any non-200 as an outage. This adapter restores a stable, deterministic contract for legacy consumers without changing the backend or legacy client.


## What changed (observed variants)

- 200 with full user object (expected)
- 200 with `email` omitted
- 200 with `email` present but redacted (`"***REDACTED***"`)
- 401 JSON error (Unauthorized)
- 429 JSON error (Too Many Requests)

These mixed responses broke legacy clients that expect `email` (valid email) and `about_me` (string) to always be present.


## Mitigation strategy

- Introduce a compatibility layer (this repository) that:
  - Normalizes all successful 2xx responses into the legacy `UserStrict` shape
  - Synthesizes deterministic emails for missing/redacted values: `<username>@unknown.local`
  - Ensures `about_me` is always a string (defaults to `""`)
  - Converts error responses (401, 429, others) into a legacy-friendly body while returning HTTP 200 to avoid legacy monitoring false-positives
  - Adds a `_classification` field for monitoring: `OK`, `CLIENT_ERROR`, `TRANSIENT`, `OUTAGE`
  - Is idempotent: applying normalization repeatedly does not change the result


## Key tradeoffs & limitations

- Adapter returns HTTP 200 for upstream 401/429 to avoid triggering legacy monitoring. This intentionally hides non-200 upstream statuses from the legacy client; the adapter exposes classification metadata so monitoring can still distinguish error types.
- The adapter synthesizes data (emails). This is a backward-compatible shim and not intended as a permanent data fix.
- Backend and legacy client remain unchanged — this is a short-to-medium term mitigation.


## Files

- `adapter.py` — normalization logic (idempotent)
- `legacy_client.py` — simulated legacy client (unchangeable)
- `test_adapter.py` — pytest suite covering regressions, normalization, and idempotency
- `input.py` — sample upstream responses (provided)
- `run_tests` — one-command test runner
- `requirements.txt` — test dependencies


## How to run

1. (Optional) Create & activate a Python virtualenv
2. Install requirements (optional — `run_tests` will install if pytest missing):
   python -m pip install -r requirements.txt
3. Run the test suite (single command):
   python run_tests


## Interpreting test results

- Tests demonstrate legacy client failures against raw upstream payloads, and show that the adapter restores compatibility for all observed variants.
- Tests also verify idempotency: normalizing an already-normalized payload is a no-op.


## Example behavior

- Upstream: `200 {id:2, username:"bob", about_me:"Hi"}`
  -> Adapter: `200 {id:2, username:"bob", email:"bob@unknown.local", about_me:"Hi", last_seen:"", _classification:"OK"}`

- Upstream: `401 {error:"Unauthorized", message:"..."}`
  -> Adapter: `200 {id:0, username:"", email:"unknown@unknown.local", about_me:"", last_seen:"", error:"Unauthorized", message:"...", _classification:"CLIENT_ERROR"}`


## Next steps (recommended)

- Deploy adapter as a reverse-proxy / API gateway rule in front of `/api/users/<id>`.
- Instrument monitoring to use `_classification` rather than HTTP status for this endpoint.
- Fix the backend to restore a stable schema and add versioning/feature flags to avoid silent contract changes.


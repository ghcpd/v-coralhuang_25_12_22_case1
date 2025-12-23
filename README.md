# Compatibility layer for /api/users/{id}

✅ Purpose: restore a stable, backward-compatible contract for legacy clients while the
upstream API returns inconsistent response shapes.

## Problem (summary)
- Upstream `GET /api/users/{id}` returns multiple successful (2xx) shapes for the same
  resource (missing `email`, redacted `email`, different types for `about_me`).
- Legacy clients assume a stable schema and treat any non-200 as an outage.
- This caused production regressions for legacy consumers.

## Mitigation strategy
- Deploy a compatibility proxy that sits between legacy clients and the upstream API.
- The proxy normalizes *all* upstream responses into a deterministic, idempotent
  schema containing the core fields legacy clients expect: `id`, `username`,
  `email`, `about_me`, `last_seen`.
- Upstream errors are transformed into a best-effort user payload (HTTP 200) plus
  structured `meta` information for monitoring and alerting. This prevents false
  outage signals while surfacing the true condition to observability tooling.

## Key trade-offs & limitations
- Returning HTTP 200 for upstream errors preserves legacy behavior (avoids outages)
  but changes semantics for newer integrations that rely on status codes.
- The proxy synthesizes deterministic placeholder values (e.g. placeholder emails).
  These are not the real user data and should not be relied on by systems that
  require authoritative information.
- This is an emergency compatibility shim — upstream should be fixed and versioned.

## Files
- `app.py` — FastAPI compatibility proxy exposing `GET /api/users/{id}`
- `compat.py` — deterministic normalization logic (idempotent)
- `tests/test_compat.py` — comprehensive unit + integration tests
- `requirements.txt` — minimal dependencies
- `run_tests` — one-command test runner

## How to run locally
1. Create a virtualenv and install deps:
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt

2. Run tests (single command):
   python run_tests

## How this meets the requirements
- Restores stable schema for legacy clients (core fields always present)
- Normalizes error responses into structured `meta` + deterministic fallback fields
- Idempotent normalization (safe to apply multiple times)
- Tests demonstrate legacy failure on raw upstream data and success behind the shim

## Operational recommendations
- Add an HTTP healthcheck that inspects `meta.classification` to surface real
  upstream outages to SRE (do not rely on HTTP status alone).
- Add rate-limit and circuit-breaker to the proxy to protect upstream.
- Plan to deprecate this shim once upstream is fixed and clients migrated.

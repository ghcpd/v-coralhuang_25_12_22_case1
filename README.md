# API Compatibility Layer for /api/users/<id>

## API Bug Description

The endpoint `GET /api/users/<id>` exhibits schema instability, returning different response structures for the same HTTP method and path depending on request context. This violates API contract expectations and breaks legacy clients that assume stable schemas for successful (2xx) responses.

### Observed Variants

1. **200 OK** - Full user object with `email`
2. **200 OK** - User object missing `email` field
3. **200 OK** - User object with `email: "***REDACTED***"`
4. **401 Unauthorized** - JSON error response
5. **429 Too Many Requests** - JSON error with retry info

### Impact on Legacy Clients

Legacy clients assume:
- Successful responses have consistent schema with required fields: `id`, `username`, `email`, `about_me`, `last_seen`
- `email` is always present and contains '@' (valid email format)
- `about_me` is always a string (never null)
- Any non-200 response indicates a service outage

The API bug causes:
- Missing `email` fields break client parsing
- Redacted emails are invalid format
- Null `about_me` causes type errors
- Error responses treated as outages trigger false alerts

## Mitigation Strategy

A compatibility layer normalizes all responses to restore stable contracts:

### Successful Responses (200)
- Synthesize missing/redacted emails as `<username>@unknown.local`
- Convert null `about_me` to empty string `""`
- Ensure all required fields present

### Error Responses (401/429)
- Normalize to consistent `{"error": "<short>", "message": "<detail>"}` format
- Classify for monitoring: `CLIENT_ERROR` (401), `TRANSIENT` (429)

### Properties
- **Idempotent**: Safe to apply multiple times
- **Deterministic**: Same input always produces same output
- **Non-breaking**: Preserves all original data where possible

## Key Tradeoffs and Limitations

- Synthetic emails are not real but satisfy format requirements
- Error normalization loses original response details (but maintains essential info)
- Assumes only observed variants; other unhandled errors classified as `UNKNOWN_ERROR`
- Requires response parsing before normalization

## Setup

1. Install Python 3.8+
2. Install dependencies: `pip install -r requirements.txt`

## Running Tests

Execute `run_tests.bat` (Windows) or `python -m pytest test_compatibility.py -v` (cross-platform)

Tests demonstrate:
- Raw API responses fail legacy compatibility
- Normalized responses pass legacy checks
- Normalization is idempotent
- All variants handled correctly

## Test Output Interpretation

- **PASS**: All tests pass, compatibility layer working
- **FAIL**: Indicates bugs in normalization logic
- Non-zero exit code on failure for CI/CD integration
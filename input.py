# === Context ===
# Backend API: /api/users/<id>
# No versioning in URL
# Same endpoint, same method, different response schema depending on context
# Additional regressions introduced recently (non-breaking at HTTP layer, breaking at contract layer)

# === Variant A: User requests their own profile ===
# GET /api/users/1
# Authorization: Bearer <token-for-user-1>
response_self = {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com",
    "about_me": "Hello, I'm Alice",
    "last_seen": "2024-12-01T10:00:00Z",
    "_links": {"self": "/api/users/1"}
}

# === Variant B: User requests another user's profile ===
# GET /api/users/2
# Authorization: Bearer <token-for-user-1>
# Regression: email omitted entirely
response_other = {
    "id": 2,
    "username": "bob",
    "about_me": "Hi, I'm Bob",
    "last_seen": "2024-11-30T18:20:00Z",
    "_links": {"self": "/api/users/2"}
}

# === Variant C: Same endpoint, partial visibility due to privacy policy rollout ===
# GET /api/users/3
# Authorization: Bearer <token-for-user-1>
# Regression: email present but redacted (string), not a real email
response_other_redacted = {
    "id": 3,
    "username": "carol",
    "email": "***REDACTED***",
    "about_me": None,
    "last_seen": "2024-11-28T08:00:00Z",
    "_links": {"self": "/api/users/3"}
}

# === Variant D: Anonymous access (Accept: application/json), same endpoint ===
# GET /api/users/4
# No Authorization header
# Regression: server returns JSON error body (still valid JSON), but schema differs
response_unauth = {
    "error": "Unauthorized",
    "message": "Missing or invalid token"
}
http_status_unauth = 401

# === Variant E: Rate-limited access (retry suggested) ===
# GET /api/users/5
response_rate_limited = {
    "error": "Too Many Requests",
    "message": "Rate limit exceeded",
    "retry_after_seconds": 2
}
http_status_rate_limited = 429

# === Legacy client expectations (strict, cannot be changed) ===
# - Client expects stable schema for successful 200 responses
# - Client expects email to exist AND be a valid email string (contains '@')
# - Client assumes about_me is always a string (not null)
# - Client treats ANY non-200 from /api/users/<id> as outage (monitoring bug)
#
# UserStrict {
#   id: int
#   username: str
#   email: str            # required, must look like an email
#   about_me: str         # required
#   last_seen: str        # required ISO-8601
# }

# === Hard constraints for the agent ===
# - You CANNOT modify the backend API behavior
# - You CANNOT modify the legacy client code or its schema
# - You MUST implement a compatibility layer (adapter/normalizer) in front of the client
# - Compatibility layer must:
#   1) Normalize all successful user responses into the legacy schema
#   2) Normalize error responses into a single legacy-friendly format
#   3) Classify responses for monitoring so legacy monitoring doesn't treat deprecation-like issues as outages
#
# === Expected behavior for the compatibility layer ===
# - For missing email: provide a deterministic synthetic email: "<username>@unknown.local"
# - For redacted email: treat as missing and synthesize
# - For about_me null: default to empty string ""
# - For 401/429: return legacy error shape: {"error": "<short>", "message": "<detail>"} and provide classification:
#     - 401 => CLIENT_ERROR
#     - 429 => TRANSIENT (retryable)
# - Must be idempotent: applying normalization twice yields identical result
# - Must produce a consistent contract for downstream analytics:
#     - always output keys: id, username, email, about_me, last_seen

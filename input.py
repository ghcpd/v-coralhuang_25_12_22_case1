# === Context ===
# Backend API: /api/users/<id>
# No versioning in URL
# Same endpoint, same method, different response schema depending on context

# === Case A: User requests their own profile ===
# GET /api/users/1
# Authorization: Bearer <token-for-user-1>

response_self = {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com",
    "about_me": "Hello, I'm Alice",
    "last_seen": "2024-12-01T10:00:00Z",
    "_links": {
        "self": "/api/users/1"
    }
}

# === Case B: User requests another user's profile ===
# GET /api/users/2
# Authorization: Bearer <token-for-user-1>

response_other = {
    "id": 2,
    "username": "bob",
    "about_me": "Hi, I'm Bob",
    "last_seen": "2024-11-30T18:20:00Z",
    "_links": {
        "self": "/api/users/2"
    }
}

# === Legacy client expectations ===
# - Same endpoint always returns the same schema
# - 'email' field is assumed to always exist
# - Client performs strict deserialization:
#
# User {
#   id: int
#   username: str
#   email: str   # required
#   about_me: str | null
#   last_seen: str
# }

# === Observed failures ===
# - Null pointer / KeyError when accessing response_other["email"]
# - Analytics pipeline drops records without email
# - No HTTP error returned (status 200)

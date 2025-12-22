# compatibility.py
"""
Compatibility layer for API /api/users/<id> to normalize responses
for legacy clients due to schema instability bug.
"""

def normalize_user_response(response):
    """
    Normalize successful user response to legacy schema.
    
    - Ensure email is present and valid (synthesize if missing/redacted)
    - Ensure about_me is a string (default to "" if None)
    - Preserve all other fields
    """
    if not isinstance(response, dict):
        raise ValueError("Response must be a dict")
    
    normalized = response.copy()
    
    # Handle email
    email = normalized.get('email')
    if not email or email == '***REDACTED***':
        username = normalized.get('username', 'unknown')
        normalized['email'] = f"{username}@unknown.local"
    
    # Handle about_me
    if normalized.get('about_me') is None:
        normalized['about_me'] = ""
    
    # Ensure required keys exist (though they should based on API)
    required_keys = ['id', 'username', 'email', 'about_me', 'last_seen']
    for key in required_keys:
        if key not in normalized:
            raise ValueError(f"Missing required key: {key}")
    
    return normalized

def normalize_error_response(status_code, response):
    """
    Normalize error responses to legacy-friendly format.
    """
    if status_code == 401:
        return {
            "error": "Unauthorized",
            "message": "Missing or invalid token"
        }, "CLIENT_ERROR"
    elif status_code == 429:
        return {
            "error": "Too Many Requests", 
            "message": "Rate limit exceeded"
        }, "TRANSIENT"
    else:
        # For other errors, return as-is but classify as UNKNOWN_ERROR
        return response, "UNKNOWN_ERROR"

def normalize_response(status_code, response):
    """
    Main normalization function.
    
    Returns: (normalized_response, classification)
    
    For 200: normalized user dict, "SUCCESS"
    For 401/429: normalized error dict, classification
    """
    if status_code == 200:
        return normalize_user_response(response), "SUCCESS"
    else:
        return normalize_error_response(status_code, response)
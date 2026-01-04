"""
API Compatibility Layer for Legacy Client Support

Mitigates schema instability in GET /api/users/<id> endpoint by normalizing
responses to a stable contract expected by legacy clients.

Guarantees:
- Deterministic and idempotent normalization
- Consistent schema for successful (2xx) responses
- Normalized error responses with classification
- Safe to apply multiple times
"""

import json
import hashlib
import re
from typing import Dict, Any, Union, Literal
from dataclasses import dataclass, asdict


@dataclass
class NormalizedUser:
    """Legacy-compatible user schema."""
    id: int
    username: str
    email: str
    about_me: str
    last_seen: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedError:
    """Legacy-compatible error response."""
    error: str
    message: str
    classification: Literal["CLIENT_ERROR", "TRANSIENT", "SERVER_ERROR"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.error,
            "message": self.message,
            "classification": self.classification
        }


def is_valid_email(email: str) -> bool:
    """
    Validate email format for legacy compatibility.
    Legacy clients expect email to contain '@' at minimum.
    """
    return isinstance(email, str) and "@" in email


def _generate_synthetic_email(username: str) -> str:
    """
    Generate deterministic synthetic email for missing/redacted cases.
    Uses simple username-based mapping to maintain idempotency.
    """
    return f"{username}@unknown.local"


def normalize_user_response(raw_response: Dict[str, Any]) -> NormalizedUser:
    """
    Normalize successful user API response to legacy schema.
    
    Handles:
    - Missing email field -> synthesize deterministically
    - Redacted email ("***REDACTED***") -> treat as missing
    - None about_me -> empty string
    - Ensures all required fields present and valid
    
    Args:
        raw_response: Raw API response dict
        
    Returns:
        NormalizedUser matching legacy contract
        
    Raises:
        KeyError: If required fields (id, username, last_seen) missing
        TypeError: If id is not int or username not string
    """
    # Extract required fields with validation
    user_id = raw_response.get("id")
    username = raw_response.get("username")
    last_seen = raw_response.get("last_seen")
    
    if not isinstance(user_id, int):
        raise TypeError(f"id must be int, got {type(user_id).__name__}")
    if not isinstance(username, str):
        raise TypeError(f"username must be str, got {type(username).__name__}")
    if not isinstance(last_seen, str):
        raise TypeError(f"last_seen must be str, got {type(last_seen).__name__}")
    
    # Handle email: missing or redacted -> synthesize
    email = raw_response.get("email")
    if not is_valid_email(email):
        # Missing or invalid email -> synthesize deterministically
        email = _generate_synthetic_email(username)
    
    # Handle about_me: None or missing -> empty string
    about_me = raw_response.get("about_me")
    if about_me is None or not isinstance(about_me, str):
        about_me = ""
    
    return NormalizedUser(
        id=user_id,
        username=username,
        email=email,
        about_me=about_me,
        last_seen=last_seen
    )


def normalize_error_response(
    http_status: int,
    raw_response: Dict[str, Any]
) -> NormalizedError:
    """
    Normalize error response to legacy-friendly format with classification.
    
    Classifications:
    - 401 -> CLIENT_ERROR (authentication failure, client's responsibility to fix)
    - 429 -> TRANSIENT (rate limit, safe to retry)
    - 5xx or other -> SERVER_ERROR (backend issue, not client's responsibility)
    
    Args:
        http_status: HTTP status code
        raw_response: Raw error response dict
        
    Returns:
        NormalizedError with classification for monitoring
    """
    error_short = raw_response.get("error", "Error")
    message_detail = raw_response.get("message", "An error occurred")
    
    # Classify for monitoring to prevent false outage alerts
    if http_status == 401:
        classification = "CLIENT_ERROR"
    elif http_status == 429:
        classification = "TRANSIENT"
    else:
        classification = "SERVER_ERROR"
    
    return NormalizedError(
        error=error_short,
        message=message_detail,
        classification=classification
    )


def apply_compatibility_layer(
    raw_response: Dict[str, Any],
    http_status: int
) -> Union[Dict[str, Any], NormalizedError]:
    """
    Main entry point for compatibility layer.
    
    Determines if response is success (2xx) or error and applies
    appropriate normalization.
    
    Guarantees idempotency: applying this function twice to same input
    yields identical output.
    
    Args:
        raw_response: Raw API response
        http_status: HTTP status code
        
    Returns:
        If 2xx: dict matching legacy user schema
        If error: NormalizedError with classification
    """
    if 200 <= http_status < 300:
        # Successful response: normalize user data
        normalized = normalize_user_response(raw_response)
        return normalized.to_dict()
    else:
        # Error response: normalize and classify
        normalized_error = normalize_error_response(http_status, raw_response)
        return normalized_error.to_dict()


def is_idempotent(
    raw_response: Dict[str, Any],
    http_status: int
) -> bool:
    """
    Verify idempotency: applying normalization twice yields same result.
    
    Args:
        raw_response: Raw API response
        http_status: HTTP status code
        
    Returns:
        True if applying normalization twice yields identical result
    """
    try:
        first_pass = apply_compatibility_layer(raw_response, http_status)
        # For second pass, treat the normalized output as raw input
        second_pass = apply_compatibility_layer(first_pass, http_status)
        
        # Compare as JSON to handle dict ordering
        first_json = json.dumps(first_pass, sort_keys=True)
        second_json = json.dumps(second_pass, sort_keys=True)
        
        return first_json == second_json
    except Exception:
        return False

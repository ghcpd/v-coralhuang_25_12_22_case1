# test_compatibility.py
"""
Tests for the compatibility layer.
"""

import pytest
from compatibility import normalize_response

# Test data from input.py
response_self = {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com",
    "about_me": "Hello, I'm Alice",
    "last_seen": "2024-12-01T10:00:00Z",
    "_links": {"self": "/api/users/1"}
}

response_other = {
    "id": 2,
    "username": "bob",
    "about_me": "Hi, I'm Bob",
    "last_seen": "2024-11-30T18:20:00Z",
    "_links": {"self": "/api/users/2"}
}

response_other_redacted = {
    "id": 3,
    "username": "carol",
    "email": "***REDACTED***",
    "about_me": None,
    "last_seen": "2024-11-28T08:00:00Z",
    "_links": {"self": "/api/users/3"}
}

response_unauth = {
    "error": "Unauthorized",
    "message": "Missing or invalid token"
}

response_rate_limited = {
    "error": "Too Many Requests",
    "message": "Rate limit exceeded",
    "retry_after_seconds": 2
}

def is_legacy_compatible(response):
    """
    Check if response matches legacy client expectations for successful responses.
    """
    if not isinstance(response, dict):
        return False
    
    required_keys = {'id', 'username', 'email', 'about_me', 'last_seen'}
    if not all(k in response for k in required_keys):
        return False
    
    # email must be string and contain '@'
    email = response['email']
    if not isinstance(email, str) or '@' not in email:
        return False
    
    # about_me must be string
    if not isinstance(response['about_me'], str):
        return False
    
    # id should be int, but we'll assume it is
    return True

def is_legacy_error_compatible(response):
    """
    Check if error response matches normalized format.
    """
    if not isinstance(response, dict):
        return False
    
    if 'error' not in response or 'message' not in response:
        return False
    
    if not isinstance(response['error'], str) or not isinstance(response['message'], str):
        return False
    
    return True

class TestCompatibilityLayer:
    
    def test_variant_a_full_response(self):
        """Test Variant A: Full response with email"""
        normalized, classification = normalize_response(200, response_self)
        assert classification == "SUCCESS"
        assert is_legacy_compatible(normalized)
        # Should remain unchanged
        assert normalized['email'] == "alice@example.com"
        assert normalized['about_me'] == "Hello, I'm Alice"
    
    def test_variant_b_missing_email(self):
        """Test Variant B: Missing email"""
        normalized, classification = normalize_response(200, response_other)
        assert classification == "SUCCESS"
        assert is_legacy_compatible(normalized)
        # Email should be synthesized
        assert normalized['email'] == "bob@unknown.local"
        assert normalized['about_me'] == "Hi, I'm Bob"
    
    def test_variant_c_redacted_email(self):
        """Test Variant C: Redacted email"""
        normalized, classification = normalize_response(200, response_other_redacted)
        assert classification == "SUCCESS"
        assert is_legacy_compatible(normalized)
        # Email should be synthesized
        assert normalized['email'] == "carol@unknown.local"
        assert normalized['about_me'] == ""
    
    def test_variant_d_unauthorized(self):
        """Test Variant D: 401 Unauthorized"""
        normalized, classification = normalize_response(401, response_unauth)
        assert classification == "CLIENT_ERROR"
        assert is_legacy_error_compatible(normalized)
        assert normalized['error'] == "Unauthorized"
        assert normalized['message'] == "Missing or invalid token"
    
    def test_variant_e_rate_limited(self):
        """Test Variant E: 429 Rate Limited"""
        normalized, classification = normalize_response(429, response_rate_limited)
        assert classification == "TRANSIENT"
        assert is_legacy_error_compatible(normalized)
        assert normalized['error'] == "Too Many Requests"
        assert normalized['message'] == "Rate limit exceeded"
    
    def test_idempotency(self):
        """Test that normalization is idempotent"""
        # Test successful response
        first, _ = normalize_response(200, response_other)
        second, _ = normalize_response(200, first)
        assert first == second
        
        # Test error response
        first, _ = normalize_response(401, response_unauth)
        second, _ = normalize_response(401, first)
        assert first == second
    
    def test_legacy_failures_without_normalization(self):
        """Demonstrate that raw responses fail legacy compatibility"""
        # Variant B missing email
        assert not is_legacy_compatible(response_other)
        
        # Variant C redacted email and null about_me
        assert not is_legacy_compatible(response_other_redacted)
        
        # Errors are not user objects, so fail legacy user check
        assert not is_legacy_compatible(response_unauth)
        assert not is_legacy_compatible(response_rate_limited)
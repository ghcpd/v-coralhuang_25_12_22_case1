"""
Comprehensive test suite for API compatibility layer.

Tests cover:
1. All response variants (A-E from input.py)
2. Legacy client failures before normalization
3. Success after applying compatibility layer
4. Idempotency guarantee
5. Edge cases and error handling
"""

import unittest
import json
from compatibility_layer import (
    apply_compatibility_layer,
    normalize_user_response,
    normalize_error_response,
    is_idempotent,
    NormalizedUser,
    NormalizedError,
    is_valid_email
)


class TestLegacyClientFailures(unittest.TestCase):
    """
    Demonstrate how legacy clients fail without normalization.
    Legacy client schema: {id, username, email, about_me, last_seen}
    Constraints: email must be valid, about_me must be string.
    """

    def test_variant_b_missing_email_breaks_legacy(self):
        """
        Variant B: email field missing entirely.
        Legacy client expects email to always exist -> breaks.
        """
        response_b = {
            "id": 2,
            "username": "bob",
            "about_me": "Hi, I'm Bob",
            "last_seen": "2024-11-30T18:20:00Z",
        }
        
        # Legacy client tries to access response["email"]
        with self.assertRaises(KeyError):
            _ = response_b["email"]

    def test_variant_c_redacted_email_fails_validation(self):
        """
        Variant C: email="***REDACTED***"
        Legacy client validates email contains '@' -> fails.
        """
        response_c = {
            "id": 3,
            "username": "carol",
            "email": "***REDACTED***",
            "about_me": None,
            "last_seen": "2024-11-28T08:00:00Z",
        }
        
        # Legacy validation expects valid email format
        email = response_c.get("email", "")
        has_at = "@" in email
        self.assertFalse(has_at, "Redacted email fails '@' validation")
        
        # Also about_me is None, not string
        about_me = response_c["about_me"]
        self.assertIsNone(about_me, "about_me is None, not string")

    def test_variant_a_succeeds_initially(self):
        """
        Variant A: Complete valid response.
        This is the happy case that legacy client expects.
        """
        response_a = {
            "id": 1,
            "username": "alice",
            "email": "alice@example.com",
            "about_me": "Hello, I'm Alice",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        # Legacy client can read all fields
        self.assertEqual(response_a["id"], 1)
        self.assertIn("@", response_a["email"])
        self.assertIsInstance(response_a["about_me"], str)


class TestCompatibilityNormalization(unittest.TestCase):
    """
    Test that compatibility layer fixes all variants.
    """

    def test_variant_a_normalized(self):
        """Variant A: Complete response -> normalized with all fields."""
        response_a = {
            "id": 1,
            "username": "alice",
            "email": "alice@example.com",
            "about_me": "Hello, I'm Alice",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        normalized = apply_compatibility_layer(response_a, 200)
        
        # Verify all required fields present
        self.assertIn("id", normalized)
        self.assertIn("username", normalized)
        self.assertIn("email", normalized)
        self.assertIn("about_me", normalized)
        self.assertIn("last_seen", normalized)
        
        # Verify values
        self.assertEqual(normalized["id"], 1)
        self.assertEqual(normalized["username"], "alice")
        self.assertEqual(normalized["email"], "alice@example.com")
        self.assertIn("@", normalized["email"])

    def test_variant_b_missing_email_synthesized(self):
        """Variant B: Missing email -> synthesized deterministically."""
        response_b = {
            "id": 2,
            "username": "bob",
            "about_me": "Hi, I'm Bob",
            "last_seen": "2024-11-30T18:20:00Z",
        }
        
        normalized = apply_compatibility_layer(response_b, 200)
        
        # Email should be synthesized
        self.assertIn("email", normalized)
        self.assertIn("@", normalized["email"])
        # Should be deterministic based on username
        self.assertEqual(normalized["email"], "bob@unknown.local")

    def test_variant_c_redacted_email_handled(self):
        """Variant C: Redacted email -> treated as missing, synthesized."""
        response_c = {
            "id": 3,
            "username": "carol",
            "email": "***REDACTED***",
            "about_me": None,
            "last_seen": "2024-11-28T08:00:00Z",
        }
        
        normalized = apply_compatibility_layer(response_c, 200)
        
        # Redacted email should be synthesized
        self.assertIn("@", normalized["email"])
        self.assertEqual(normalized["email"], "carol@unknown.local")
        
        # None about_me should become empty string
        self.assertEqual(normalized["about_me"], "")
        self.assertIsInstance(normalized["about_me"], str)

    def test_variant_d_unauth_error_normalized(self):
        """Variant D: 401 error -> normalized with classification."""
        response_d = {
            "error": "Unauthorized",
            "message": "Missing or invalid token"
        }
        
        normalized = apply_compatibility_layer(response_d, 401)
        
        # Should have legacy error shape
        self.assertIn("error", normalized)
        self.assertIn("message", normalized)
        self.assertIn("classification", normalized)
        
        # Should be classified as CLIENT_ERROR
        self.assertEqual(normalized["classification"], "CLIENT_ERROR")

    def test_variant_e_rate_limit_normalized(self):
        """Variant E: 429 error -> normalized as TRANSIENT."""
        response_e = {
            "error": "Too Many Requests",
            "message": "Rate limit exceeded",
            "retry_after_seconds": 2
        }
        
        normalized = apply_compatibility_layer(response_e, 429)
        
        # Should have legacy error shape
        self.assertIn("error", normalized)
        self.assertIn("message", normalized)
        self.assertIn("classification", normalized)
        
        # Should be classified as TRANSIENT
        self.assertEqual(normalized["classification"], "TRANSIENT")


class TestIdempotency(unittest.TestCase):
    """
    Verify idempotency: applying normalization twice = same result.
    Safety guarantee for production use.
    """

    def test_idempotent_variant_a(self):
        """Applying normalization twice to Variant A yields same result."""
        response_a = {
            "id": 1,
            "username": "alice",
            "email": "alice@example.com",
            "about_me": "Hello, I'm Alice",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        first = apply_compatibility_layer(response_a, 200)
        second = apply_compatibility_layer(first, 200)
        
        # Should be identical
        self.assertEqual(json.dumps(first, sort_keys=True),
                        json.dumps(second, sort_keys=True))

    def test_idempotent_variant_b(self):
        """Applying normalization twice to Variant B (missing email)."""
        response_b = {
            "id": 2,
            "username": "bob",
            "about_me": "Hi, I'm Bob",
            "last_seen": "2024-11-30T18:20:00Z",
        }
        
        first = apply_compatibility_layer(response_b, 200)
        second = apply_compatibility_layer(first, 200)
        
        self.assertEqual(json.dumps(first, sort_keys=True),
                        json.dumps(second, sort_keys=True))

    def test_idempotent_variant_c(self):
        """Applying normalization twice to Variant C (redacted email + null about_me)."""
        response_c = {
            "id": 3,
            "username": "carol",
            "email": "***REDACTED***",
            "about_me": None,
            "last_seen": "2024-11-28T08:00:00Z",
        }
        
        first = apply_compatibility_layer(response_c, 200)
        second = apply_compatibility_layer(first, 200)
        
        self.assertEqual(json.dumps(first, sort_keys=True),
                        json.dumps(second, sort_keys=True))

    def test_idempotent_error_401(self):
        """Applying normalization twice to 401 error."""
        response_d = {
            "error": "Unauthorized",
            "message": "Missing or invalid token"
        }
        
        first = apply_compatibility_layer(response_d, 401)
        second = apply_compatibility_layer(first, 401)
        
        self.assertEqual(json.dumps(first, sort_keys=True),
                        json.dumps(second, sort_keys=True))

    def test_idempotent_error_429(self):
        """Applying normalization twice to 429 error."""
        response_e = {
            "error": "Too Many Requests",
            "message": "Rate limit exceeded",
            "retry_after_seconds": 2
        }
        
        first = apply_compatibility_layer(response_e, 429)
        second = apply_compatibility_layer(first, 429)
        
        self.assertEqual(json.dumps(first, sort_keys=True),
                        json.dumps(second, sort_keys=True))

    def test_is_idempotent_helper_all_variants(self):
        """Test is_idempotent() helper across all variants."""
        variants = [
            ({"id": 1, "username": "alice", "email": "alice@example.com",
              "about_me": "Hello", "last_seen": "2024-12-01T10:00:00Z"}, 200),
            ({"id": 2, "username": "bob", "about_me": "Hi", 
              "last_seen": "2024-11-30T18:20:00Z"}, 200),
            ({"id": 3, "username": "carol", "email": "***REDACTED***",
              "about_me": None, "last_seen": "2024-11-28T08:00:00Z"}, 200),
            ({"error": "Unauthorized", "message": "Missing or invalid token"}, 401),
            ({"error": "Too Many Requests", "message": "Rate limit exceeded"}, 429),
        ]
        
        for response, status in variants:
            self.assertTrue(is_idempotent(response, status),
                          f"Not idempotent for {status}: {response}")


class TestEdgeCases(unittest.TestCase):
    """
    Test edge cases and boundary conditions.
    """

    def test_empty_about_me_string_preserved(self):
        """Empty string about_me should be preserved, not converted to None."""
        response = {
            "id": 5,
            "username": "dave",
            "email": "dave@example.com",
            "about_me": "",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        normalized = apply_compatibility_layer(response, 200)
        self.assertEqual(normalized["about_me"], "")
        self.assertIsInstance(normalized["about_me"], str)

    def test_missing_about_me_becomes_empty_string(self):
        """Missing about_me field becomes empty string."""
        response = {
            "id": 6,
            "username": "eve",
            "email": "eve@example.com",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        normalized = apply_compatibility_layer(response, 200)
        self.assertEqual(normalized["about_me"], "")

    def test_zero_id_valid(self):
        """ID of 0 is technically valid (edge case)."""
        response = {
            "id": 0,
            "username": "zero",
            "email": "zero@example.com",
            "about_me": "I am zero",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        normalized = apply_compatibility_layer(response, 200)
        self.assertEqual(normalized["id"], 0)

    def test_special_chars_in_username_for_email(self):
        """Special characters in username -> deterministic email generation."""
        response = {
            "id": 7,
            "username": "alice_2024",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        normalized = apply_compatibility_layer(response, 200)
        # Should be deterministic
        self.assertEqual(normalized["email"], "alice_2024@unknown.local")

    def test_very_long_about_me(self):
        """Very long about_me string preserved."""
        long_text = "x" * 10000
        response = {
            "id": 8,
            "username": "longwinded",
            "email": "long@example.com",
            "about_me": long_text,
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        normalized = apply_compatibility_layer(response, 200)
        self.assertEqual(normalized["about_me"], long_text)

    def test_5xx_error_classified_as_server_error(self):
        """5xx errors classified as SERVER_ERROR."""
        response = {
            "error": "Internal Server Error",
            "message": "Something went wrong"
        }
        
        normalized = apply_compatibility_layer(response, 500)
        self.assertEqual(normalized["classification"], "SERVER_ERROR")


class TestErrorClassification(unittest.TestCase):
    """
    Test error classification for monitoring.
    Prevents false outage alerts for client/transient errors.
    """

    def test_401_client_error(self):
        """401 classified as CLIENT_ERROR."""
        response = {"error": "Unauthorized", "message": "Bad token"}
        normalized = apply_compatibility_layer(response, 401)
        self.assertEqual(normalized["classification"], "CLIENT_ERROR")

    def test_429_transient(self):
        """429 classified as TRANSIENT (retryable)."""
        response = {"error": "Too Many Requests", "message": "Rate limited"}
        normalized = apply_compatibility_layer(response, 429)
        self.assertEqual(normalized["classification"], "TRANSIENT")

    def test_403_server_error(self):
        """403 Forbidden classified as SERVER_ERROR (not CLIENT_ERROR)."""
        response = {"error": "Forbidden", "message": "Access denied"}
        normalized = apply_compatibility_layer(response, 403)
        self.assertEqual(normalized["classification"], "SERVER_ERROR")

    def test_500_server_error(self):
        """500 classified as SERVER_ERROR."""
        response = {"error": "Internal Server Error", "message": "Crashed"}
        normalized = apply_compatibility_layer(response, 500)
        self.assertEqual(normalized["classification"], "SERVER_ERROR")

    def test_503_server_error(self):
        """503 classified as SERVER_ERROR."""
        response = {"error": "Service Unavailable", "message": "Maintenance"}
        normalized = apply_compatibility_layer(response, 503)
        self.assertEqual(normalized["classification"], "SERVER_ERROR")


class TestSchemaConsistency(unittest.TestCase):
    """
    Verify that all normalized responses have consistent schema.
    """

    def test_all_required_fields_in_success(self):
        """All success responses have required fields."""
        variants = [
            {"id": 1, "username": "alice", "email": "alice@example.com",
             "about_me": "Hello", "last_seen": "2024-12-01T10:00:00Z"},
            {"id": 2, "username": "bob", "about_me": "Hi",
             "last_seen": "2024-11-30T18:20:00Z"},
            {"id": 3, "username": "carol", "email": "***REDACTED***",
             "about_me": None, "last_seen": "2024-11-28T08:00:00Z"},
        ]
        
        required_fields = {"id", "username", "email", "about_me", "last_seen"}
        
        for variant in variants:
            normalized = apply_compatibility_layer(variant, 200)
            self.assertEqual(set(normalized.keys()), required_fields,
                           f"Missing fields in {variant}")

    def test_all_error_responses_have_standard_shape(self):
        """All error responses have error, message, classification."""
        responses = [
            ({"error": "Unauthorized", "message": "Bad token"}, 401),
            ({"error": "Too Many Requests", "message": "Rate limited"}, 429),
            ({"error": "Internal Error", "message": "Crashed"}, 500),
        ]
        
        required_error_fields = {"error", "message", "classification"}
        
        for response, status in responses:
            normalized = apply_compatibility_layer(response, status)
            self.assertEqual(set(normalized.keys()), required_error_fields)


class TestInputValidation(unittest.TestCase):
    """
    Test input validation and error handling.
    """

    def test_invalid_id_type_raises(self):
        """ID must be int."""
        response = {
            "id": "not-an-int",
            "username": "alice",
            "email": "alice@example.com",
            "about_me": "Hello",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        with self.assertRaises(TypeError):
            apply_compatibility_layer(response, 200)

    def test_invalid_username_type_raises(self):
        """Username must be string."""
        response = {
            "id": 1,
            "username": 123,
            "email": "alice@example.com",
            "about_me": "Hello",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        with self.assertRaises(TypeError):
            apply_compatibility_layer(response, 200)

    def test_missing_id_raises(self):
        """ID must be present."""
        response = {
            "username": "alice",
            "email": "alice@example.com",
            "about_me": "Hello",
            "last_seen": "2024-12-01T10:00:00Z",
        }
        
        with self.assertRaises(TypeError):
            apply_compatibility_layer(response, 200)


class TestEmailValidation(unittest.TestCase):
    """
    Test email validation logic.
    """

    def test_valid_email(self):
        """Valid emails pass validation."""
        self.assertTrue(is_valid_email("alice@example.com"))
        self.assertTrue(is_valid_email("user+tag@domain.co.uk"))

    def test_missing_email_fails(self):
        """Missing/None email fails validation."""
        self.assertFalse(is_valid_email(None))

    def test_redacted_email_fails(self):
        """Redacted email fails validation."""
        self.assertFalse(is_valid_email("***REDACTED***"))

    def test_empty_string_fails(self):
        """Empty string fails validation."""
        self.assertFalse(is_valid_email(""))

    def test_no_at_sign_fails(self):
        """String without @ fails validation."""
        self.assertFalse(is_valid_email("notanemail"))


def run_tests():
    """Run all tests and return results."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestLegacyClientFailures))
    suite.addTests(loader.loadTestsFromTestCase(TestCompatibilityNormalization))
    suite.addTests(loader.loadTestsFromTestCase(TestIdempotency))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorClassification))
    suite.addTests(loader.loadTestsFromTestCase(TestSchemaConsistency))
    suite.addTests(loader.loadTestsFromTestCase(TestInputValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestEmailValidation))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == "__main__":
    result = run_tests()
    # Exit with non-zero on failure
    exit(0 if result.wasSuccessful() else 1)

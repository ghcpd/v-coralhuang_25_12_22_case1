"""Simulated legacy client that enforces the strict `UserStrict` schema.

This module is intentionally *unchangeable* in the exercise: tests will
show it failing against raw upstream responses and succeeding when used
with the compatibility adapter.
"""
from typing import Dict
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LegacyClientSchemaError(ValueError):
    pass


def validate_user_strict(payload: Dict) -> Dict:
    """Validate payload against the legacy `UserStrict` expectations.

    Raises LegacyClientSchemaError on any violation. Returns payload when
    valid (simulates the client accepting and using the data).
    """
    required = ["id", "username", "email", "about_me", "last_seen"]
    for k in required:
        if k not in payload:
            raise LegacyClientSchemaError(f"missing required field: {k}")

    if not isinstance(payload["id"], int):
        raise LegacyClientSchemaError("id must be int")
    if not isinstance(payload["username"], str):
        raise LegacyClientSchemaError("username must be str")
    if not isinstance(payload["about_me"], str):
        raise LegacyClientSchemaError("about_me must be str")
    if not isinstance(payload["last_seen"], str):
        raise LegacyClientSchemaError("last_seen must be str")

    email = payload.get("email")
    if not isinstance(email, str) or not EMAIL_RE.match(email):
        raise LegacyClientSchemaError("email must be a valid email string")

    # If all checks pass, return payload (client would proceed normally)
    return payload


# The legacy client also *treats any non-200* as an outage; to emulate that
# behavior in tests we simply raise an exception when a wrapper reports
# a non-200 status code.
class LegacyClientHTTPError(Exception):
    pass


def process_response(status_code: int, body: Dict) -> Dict:
    """Simulated legacy client entry point.

    - Raises LegacyClientHTTPError if status_code != 200 (monitoring bug)
    - Otherwise validates the payload schema strictly.
    """
    if status_code != 200:
        raise LegacyClientHTTPError(f"upstream returned non-200: {status_code}")
    return validate_user_strict(body)

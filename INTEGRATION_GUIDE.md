# Integration Guide and Examples

## Quick Start

### 1. Verify Installation

```bash
cd c:\Bug_Bash\25_12_22\v-coralhuang_25_12_22_case1
python run_tests.py
```

Expected output:
```
✓ ALL TESTS PASSED
  Ran 35 tests
```

### 2. Use in Your Code

```python
from compatibility_layer import apply_compatibility_layer
import requests

# Make API call
response = requests.get("https://api.example.com/api/users/1")
raw_body = response.json()
http_status = response.status_code

# Apply compatibility layer
normalized = apply_compatibility_layer(raw_body, http_status)

# Use normalized response - guaranteed stable schema
print(f"User: {normalized['username']} ({normalized['email']})")
```

---

## Detailed Integration Examples

### Example 1: Synchronous API Client

```python
from compatibility_layer import apply_compatibility_layer
import requests
from typing import Dict, Any

class UserAPI:
    """API client with built-in compatibility layer."""
    
    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url
        self.auth_token = auth_token
    
    def get_user(self, user_id: int) -> Dict[str, Any]:
        """
        Get user by ID with automatic normalization.
        
        Returns normalized user matching legacy schema:
        {id, username, email, about_me, last_seen}
        """
        # Make request
        url = f"{self.base_url}/api/users/{user_id}"
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        response = requests.get(url, headers=headers)
        
        # Apply compatibility layer
        normalized = apply_compatibility_layer(
            response.json(),
            response.status_code
        )
        
        return normalized

# Usage
api = UserAPI("https://api.example.com", "token123")
user = api.get_user(1)

# Safe to access all fields
print(f"ID: {user['id']}")
print(f"Username: {user['username']}")
print(f"Email: {user['email']}")  # Safe even if original was missing/redacted
print(f"Bio: {user['about_me']}")
print(f"Last seen: {user['last_seen']}")
```

---

### Example 2: With Caching (Idempotency Matters)

```python
from compatibility_layer import apply_compatibility_layer
import requests
import json
from functools import lru_cache

class CachedUserAPI:
    """API client with caching. Normalization idempotency is critical here."""
    
    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url
        self.auth_token = auth_token
        self.cache = {}  # Simple dict cache
    
    def get_user(self, user_id: int) -> dict:
        """Get user with caching."""
        cache_key = f"user:{user_id}"
        
        # Check cache
        if cache_key in self.cache:
            # Cache might be:
            # - Original raw response (not normalized)
            # - Normalized response (already normalized once)
            # - Re-cached normalized response (normalized multiple times)
            # Thanks to idempotency, all cases are safe!
            cached_data = self.cache[cache_key]
            return apply_compatibility_layer(
                cached_data,
                200  # Assume cached data is success
            )
        
        # Fetch from API
        response = requests.get(
            f"{self.base_url}/api/users/{user_id}",
            headers={"Authorization": f"Bearer {self.auth_token}"}
        )
        
        # Normalize
        normalized = apply_compatibility_layer(
            response.json(),
            response.status_code
        )
        
        # Cache the normalized response
        self.cache[cache_key] = normalized
        
        return normalized

# Usage
api = CachedUserAPI("https://api.example.com", "token123")
user1 = api.get_user(1)  # Fetches and caches
user1_again = api.get_user(1)  # Returns from cache
# Both are identical due to idempotency guarantee
assert user1 == user1_again
```

---

### Example 3: Error Handling with Classification

```python
from compatibility_layer import apply_compatibility_layer
import requests
import time

class ResilientUserAPI:
    """API client with intelligent error handling using classification."""
    
    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url
        self.auth_token = auth_token
    
    def get_user(self, user_id: int, retries: int = 3) -> dict:
        """
        Get user with intelligent retry logic based on error classification.
        """
        for attempt in range(retries):
            try:
                response = requests.get(
                    f"{self.base_url}/api/users/{user_id}",
                    headers={"Authorization": f"Bearer {self.auth_token}"},
                    timeout=5
                )
                
                normalized = apply_compatibility_layer(
                    response.json(),
                    response.status_code
                )
                
                # Check if success (2xx)
                if 200 <= response.status_code < 300:
                    return normalized
                
                # Check error classification
                classification = normalized.get("classification", "SERVER_ERROR")
                
                if classification == "TRANSIENT":
                    # 429, 408, etc. - safe to retry
                    wait_time = 2 ** attempt  # Exponential backoff
                    print(f"Rate limited. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                elif classification == "CLIENT_ERROR":
                    # 401 - authentication issue, don't retry
                    raise ValueError(f"Auth failed: {normalized['message']}")
                
                else:
                    # SERVER_ERROR - real backend issue
                    if attempt < retries - 1:
                        wait_time = 2 ** attempt
                        print(f"Server error. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(
                            f"Server error after {retries} attempts: {normalized['message']}"
                        )
                
            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    print("Request timeout. Retrying...")
                    time.sleep(2 ** attempt)
                else:
                    raise
        
        raise RuntimeError("Failed to get user after retries")

# Usage
api = ResilientUserAPI("https://api.example.com", "token123")

try:
    user = api.get_user(1)
    print(f"Got user: {user['username']}")
except ValueError as e:
    print(f"Auth error: {e}")  # Don't retry, fix auth
except RuntimeError as e:
    print(f"Failed: {e}")  # Real error, escalate
```

---

### Example 4: Async with aiohttp

```python
from compatibility_layer import apply_compatibility_layer
import aiohttp
import asyncio
from typing import Dict, Any

class AsyncUserAPI:
    """Async API client with compatibility layer."""
    
    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url
        self.auth_token = auth_token
    
    async def get_user(self, user_id: int) -> Dict[str, Any]:
        """Get user asynchronously."""
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            url = f"{self.base_url}/api/users/{user_id}"
            
            async with session.get(url, headers=headers) as response:
                data = await response.json()
                status = response.status
                
                # Apply compatibility layer
                normalized = apply_compatibility_layer(data, status)
                return normalized
    
    async def get_multiple_users(self, user_ids: list) -> list:
        """Get multiple users concurrently."""
        tasks = [self.get_user(uid) for uid in user_ids]
        return await asyncio.gather(*tasks)

# Usage
async def main():
    api = AsyncUserAPI("https://api.example.com", "token123")
    
    # Single user
    user = await api.get_user(1)
    print(f"User: {user['username']}")
    
    # Multiple users concurrently
    users = await api.get_multiple_users([1, 2, 3])
    for user in users:
        print(f"- {user['username']} ({user['email']})")

asyncio.run(main())
```

---

### Example 5: Middleware Pattern (Flask)

```python
from compatibility_layer import apply_compatibility_layer
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

class APIGateway:
    """Gateway that normalizes backend responses for legacy clients."""
    
    def __init__(self, upstream_url: str):
        self.upstream_url = upstream_url
    
    def get_user(self, user_id: int):
        """Proxy request to upstream, normalize response."""
        # Call upstream API
        upstream_response = requests.get(
            f"{self.upstream_url}/api/users/{user_id}"
        )
        
        # Apply compatibility layer
        normalized = apply_compatibility_layer(
            upstream_response.json(),
            upstream_response.status_code
        )
        
        return normalized, upstream_response.status_code

gateway = APIGateway("https://api.example.com")

@app.route("/api/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    """
    Gateway endpoint that normalizes upstream responses.
    Legacy clients can call this instead of upstream API.
    """
    try:
        normalized, status_code = gateway.get_user(user_id)
        return jsonify(normalized), status_code
    except Exception as e:
        return jsonify({"error": "Gateway Error", "message": str(e)}), 500

# Test: visit http://localhost:5000/api/users/1
if __name__ == "__main__":
    app.run(debug=True)
```

---

### Example 6: Data Pipeline (Pandas/Analytics)

```python
from compatibility_layer import apply_compatibility_layer
import requests
import pandas as pd
from typing import List, Dict, Any

class UserDataPipeline:
    """Extract and normalize user data for analytics."""
    
    def __init__(self, api_url: str, auth_token: str):
        self.api_url = api_url
        self.auth_token = auth_token
    
    def extract_users(self, user_ids: List[int]) -> pd.DataFrame:
        """
        Extract users from API and normalize to consistent schema.
        Ensures all rows have same columns for analytics.
        """
        users = []
        
        for user_id in user_ids:
            response = requests.get(
                f"{self.api_url}/api/users/{user_id}",
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            # Normalize response
            normalized = apply_compatibility_layer(
                response.json(),
                response.status_code
            )
            
            if 200 <= response.status_code < 300:
                users.append(normalized)
        
        # Convert to DataFrame
        df = pd.DataFrame(users)
        
        # Ensure all required columns present
        required_cols = ["id", "username", "email", "about_me", "last_seen"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = None
        
        return df[required_cols]
    
    def validate_schema(self, df: pd.DataFrame) -> bool:
        """Verify all rows have consistent schema."""
        required_cols = {"id", "username", "email", "about_me", "last_seen"}
        actual_cols = set(df.columns)
        
        if not required_cols.issubset(actual_cols):
            return False
        
        # Check types
        if not (df["id"].dtype == int or df["id"].dtype == "int64"):
            return False
        if df["username"].dtype != object:  # string
            return False
        if df["email"].dtype != object:  # string
            return False
        if df["about_me"].dtype != object:  # string
            return False
        
        # Check no nulls in required fields
        for col in required_cols:
            if df[col].isnull().any():
                return False
        
        return True

# Usage
pipeline = UserDataPipeline("https://api.example.com", "token123")
df = pipeline.extract_users([1, 2, 3, 4, 5])

# Guaranteed consistent schema for analytics
assert pipeline.validate_schema(df)
print(df)
# Output: consistent DataFrame with 5 rows, 5 columns, all data clean
```

---

### Example 7: Monitoring and Observability

```python
from compatibility_layer import apply_compatibility_layer
import requests
import logging

class ObservableUserAPI:
    """API client that exports structured observability data."""
    
    def __init__(self, api_url: str, auth_token: str):
        self.api_url = api_url
        self.auth_token = auth_token
        self.logger = logging.getLogger(__name__)
    
    def get_user(self, user_id: int):
        """Get user with structured logging and metrics."""
        response = requests.get(
            f"{self.api_url}/api/users/{user_id}",
            headers={"Authorization": f"Bearer {self.auth_token}"}
        )
        
        normalized = apply_compatibility_layer(
            response.json(),
            response.status_code
        )
        
        # Log with classification for monitoring
        if 200 <= response.status_code < 300:
            # Success
            self.logger.info(
                "User retrieved",
                extra={
                    "user_id": user_id,
                    "status_code": response.status_code,
                    "has_real_email": "@unknown.local" not in normalized["email"]
                }
            )
        else:
            # Error
            classification = normalized.get("classification", "SERVER_ERROR")
            severity = "ERROR" if classification == "SERVER_ERROR" else "INFO"
            
            self.logger.log(
                logging.ERROR if severity == "ERROR" else logging.INFO,
                f"API error (classification: {classification})",
                extra={
                    "user_id": user_id,
                    "status_code": response.status_code,
                    "classification": classification,
                    "error": normalized["error"],
                    "message": normalized["message"]
                }
            )
            
            # Only alert on real errors, not transient/client errors
            if classification == "SERVER_ERROR":
                self.alert_ops(response.status_code, normalized)
        
        return normalized
    
    def alert_ops(self, status_code: int, error: dict):
        """Alert ops team only on real backend failures."""
        # Send to monitoring system (e.g., PagerDuty, Slack)
        self.logger.critical(
            f"Backend error {status_code} - alerting ops",
            extra={"error": error}
        )

# Usage
api = ObservableUserAPI("https://api.example.com", "token123")

# These will log but NOT alert ops (thanks to classification)
api.get_user(1)  # Works
api.get_user(999)  # 429 rate limit
api.get_user(0)  # 401 auth error

# This would alert ops (real error)
# api.get_user(-1)  # 500 internal server error
```

---

## Common Integration Patterns

### Pattern 1: Request/Response Adapter

```python
class CompatibilityAdapter:
    """Adapter that sits between client and API."""
    
    def __init__(self, upstream_api):
        self.upstream = upstream_api
    
    def get_user(self, user_id):
        # Get from upstream
        raw = self.upstream.get_user(user_id)
        status = self.upstream.last_status_code
        
        # Normalize
        return apply_compatibility_layer(raw, status)
```

### Pattern 2: Decorator for Automatic Normalization

```python
from functools import wraps

def normalize_response(func):
    """Decorator to automatically normalize API responses."""
    @wraps(func)
    def wrapper(*args, status_code=200, **kwargs):
        raw_response = func(*args, **kwargs)
        return apply_compatibility_layer(raw_response, status_code)
    return wrapper

class API:
    @normalize_response
    def get_user(self, user_id):
        return raw_api_call(f"/users/{user_id}")
```

### Pattern 3: Context Manager for Normalized Scope

```python
from contextlib import contextmanager

@contextmanager
def normalized_api_client(api_url, auth_token):
    """Context manager providing normalized API client."""
    client = APIClient(api_url, auth_token)
    
    # Wrap all methods to auto-normalize
    original_get = client.get_user
    client.get_user = lambda uid: apply_compatibility_layer(
        original_get(uid),
        200
    )
    
    try:
        yield client
    finally:
        client.close()

# Usage
with normalized_api_client("https://api.example.com", "token") as api:
    user = api.get_user(1)
    # Already normalized
```

---

## Troubleshooting

### Issue: "Synthesized email not real"

**Problem:** Application tries to send emails to `username@unknown.local`  
**Solution:** Email is only suitable for schema validation, not sending. If you need to send emails:
- Store original email somewhere
- Only synthesize for missing/redacted cases
- Add flag to indicate synthetic emails in monitoring

### Issue: "Data mismatch with backend"

**Problem:** Normalized data doesn't match raw API  
**Solution:** This is expected. Normalization is a compatibility layer, not a data transformer:
- Synthesized emails are for legacy client compatibility
- `about_me=""` instead of `null` is intentional
- Store raw data if needed for future use

### Issue: "Performance overhead"

**Problem:** Normalization adds latency  
**Solution:** Overhead is minimal (~1ms for typical response), but cache normalized responses:
- Cache after normalization
- Use in-memory cache for hot data
- Leverage idempotency for cache misses

---

## Migration Path

Once backend API is fixed:

1. **Phase 1**: Keep compatibility layer active (no client change needed)
2. **Phase 2**: Backend releases new versioned API (e.g., `/api/v2/users/<id>`)
3. **Phase 3**: Migrate legacy clients to new endpoint
4. **Phase 4**: Deprecate compatibility layer
5. **Phase 5**: Remove compatibility layer

---

## References

- [compatibility_layer.py](compatibility_layer.py) - Implementation details
- [README.md](README.md) - Architecture and design
- [test_compatibility_layer.py](test_compatibility_layer.py) - Test examples
- [API_ANALYSIS.md](API_ANALYSIS.md) - Problem analysis


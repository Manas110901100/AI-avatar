import sys
from models import ApiKeyRequest
from api_validator import validate_api_key
from fastapi import HTTPException

# Add path
sys.path.append(r"c:\Users\manas\Desktop\Avatar Project")

print("Testing validate_api_key with valid JSON-like object...")
req = ApiKeyRequest(api_key="sk-testkey123")
try:
    result = validate_api_key(req)
    # Note: validate_api_key will try to call OpenAI. Since we don't have a real key, it might fail with AuthenticationError or similar, 
    # but we want to ensure it DOES NOT fail with "field required" or similar Pydantic error before that.
    print(f"Result (should be key): {result}")
except HTTPException as e:
    print(f"HTTPException caught: {e.detail}")
except Exception as e:
    print(f"Exception caught: {e}")

print("\nTesting validation logic flows...")
# If we get "Incorrect API key" or "Connection error", that means the Pydantic validation PASSED and it reached the logic.

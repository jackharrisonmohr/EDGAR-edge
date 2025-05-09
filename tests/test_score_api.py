import pytest
import httpx
import os

# Base URL for the locally running scoring service
# This should match how the service is run locally for testing
# e.g., uvicorn EDGAR-Edge.src.score.app:app --host 0.0.0.0 --port 8001 (if 8000 is taken)
# For CI, this might need to be configurable or use a service container.
BASE_URL = os.environ.get("SCORE_API_BASE_URL", "http://localhost:8000") 

# Sample S3 key for testing the score endpoint
# This key doesn't need to exist in S3 for the dummy model,
# but for a real model, it should point to a valid test file.
SAMPLE_S3_KEY = "raw/2023/test/sample_filing_for_api_test.json"

@pytest.mark.asyncio
async def test_health_check():
    """
    Tests the /health endpoint.
    Asserts that the status code is 200 and the response contains 'status': 'healthy'.
    """
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/health")
    
    assert response.status_code == 200
    json_response = response.json()
    assert json_response.get("status") == "healthy"
    assert "model_version" in json_response # Check if model_version is present

@pytest.mark.asyncio
async def test_score_endpoint_success():
    """
    Tests the /v1/score endpoint with a valid request.
    Asserts status code 200 and checks the response shape.
    """
    payload = {"s3_key": SAMPLE_S3_KEY}
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post("/v1/score", json=payload)

    assert response.status_code == 200
    json_response = response.json()
    
    # Check response shape and types
    assert "s3_key" in json_response
    assert isinstance(json_response["s3_key"], str)
    assert json_response["s3_key"] == SAMPLE_S3_KEY
    
    assert "sentiment_score" in json_response
    assert isinstance(json_response["sentiment_score"], float)
    # Basic check for sentiment score range, can be more specific if model behavior is known
    assert -1.0 <= json_response["sentiment_score"] <= 1.0 
    
    assert "model_version" in json_response
    assert isinstance(json_response["model_version"], str)

@pytest.mark.asyncio
async def test_score_endpoint_missing_s3_key():
    """
    Tests the /v1/score endpoint with a request missing the s3_key.
    Asserts that the status code is 400 (Bad Request) or 422 (Unprocessable Entity by FastAPI).
    FastAPI typically returns 422 for Pydantic validation errors.
    """
    payload = {} # Missing s3_key
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post("/v1/score", json=payload)
    
    assert response.status_code == 422 # FastAPI validation error for missing field
    json_response = response.json()
    assert "detail" in json_response
    # Example check for detail content, may vary based on FastAPI version
    # assert any("s3_key" in error.get("loc", []) for error in json_response["detail"])

@pytest.mark.asyncio
async def test_score_endpoint_invalid_s3_key_format_if_applicable():
    """
    Optional: Tests the /v1/score endpoint with an s3_key that might be invalid
    if specific format validation were added to ScoreRequest model (not currently).
    For now, any string is accepted by Pydantic for s3_key.
    If the S3 fetch logic itself had strict key validation that could lead to 400,
    this test would be more relevant.
    """
    # payload = {"s3_key": "this_is_not_a_valid_s3_key_format"}
    # async with httpx.AsyncClient(base_url=BASE_URL) as client:
    #     response = await client.post("/v1/score", json=payload)
    # assert response.status_code == 400 # Or 404 if S3 fetch fails cleanly
    pass # Placeholder as current s3_key is just a string

# To run these tests:
# 1. Ensure the scoring service (src/score/app.py) is running locally.
#    Example: uvicorn EDGAR-Edge.src.score.app:app --port 8000
# 2. Ensure pytest and httpx are installed in your environment (they are in src/score/pyproject.toml dev deps).
# 3. Run pytest from the root of the EDGAR-Edge project:
#    poetry run pytest tests/test_score_api.py
#    (Or if your main pyproject.toml includes these test files and deps: poetry run pytest)

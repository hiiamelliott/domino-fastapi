"""
Simple FastAPI application for deployment in Domino as a webapp.
This uses uvicorn directly, allowing us to use async endpoints and FastAPI's autodoc.

Following Domino's recommended approach for FastAPI apps with multiple endpoints:
- Sets root_path to handle reverse proxy routing
- Configures OpenAPI schema URLs correctly
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import requests
import os
import sys

import my_model

# Get the custom app path from environment variable
# In Domino v6.1+, you can set a custom path like: /apps/<custom_path_name>/
# Set this as an environment variable in your Domino webapp settings
DOMINO_APP_PATH = os.getenv("DOMINO_APP_PATH", "")

# Create FastAPI app instance with root_path if custom path is set
app_config = {
    "title": "Domino FastAPI Webapp",
    "description": "A simple FastAPI application deployed as a Domino webapp",
    "version": "1.0.0",
}

if DOMINO_APP_PATH:
    # Ensure the path starts with /apps/ and ends without trailing slash for root_path
    root_path = DOMINO_APP_PATH.rstrip("/")
    if not root_path.startswith("/"):
        root_path = "/" + root_path
    app_config["root_path"] = root_path
    print(f"FastAPI configured with root_path: {root_path}")

app = FastAPI(**app_config)


# Note: With root_path configured, FastAPI's default /openapi.json should work correctly
# No need to override it unless we need custom behavior


# Note: With root_path configured, FastAPI's default /docs should work correctly
# No need to override it

# Add CORS middleware in case Domino needs it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RandomNumberRequest(BaseModel):
    """Payload for generating a random number."""
    start: float
    stop: float


class PredictionRequest(BaseModel):
    """Request model for predictions."""
    data: RandomNumberRequest


class PredictionResponse(BaseModel):
    """Response model for predictions."""
    prediction: Any
    metadata: Dict[str, Any]


class RemotePredictionRequest(BaseModel):
    """Request body for /remoteprediction; forwarded to the remote model."""
    data: Dict[str, Any]


@app.get("/")
async def root():
    """Root endpoint - health check and info."""
    return {
        "message": "FastAPI app running in Domino",
        "status": "healthy",
        "python_version": sys.version,
        "environment_vars": {
            "DOMINO_USER": os.getenv("DOMINO_USER", "not_set"),
            "DOMINO_PROJECT_NAME": os.getenv("DOMINO_PROJECT_NAME", "not_set"),
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/remoteprediction")
async def remote_prediction(request: RemotePredictionRequest):
    """
    Forward a prediction request to a remote Domino model.

    The remote model URL is expected to have the form:
        https://<domino_url>:443/models/<model_id>/latest/model

    where:
      - <domino_url> comes from DOMINO_REMOTE_MODEL_HOST
      - <model_id> comes from DOMINO_REMOTE_MODEL_ID
    """
    remote_host = os.getenv("DOMINO_REMOTE_MODEL_HOST")
    model_id = os.getenv("DOMINO_REMOTE_MODEL_ID")
    access_token = os.getenv("DOMINO_REMOTE_MODEL_TOKEN") or None

    if not remote_host or not model_id:
        raise HTTPException(
            status_code=500,
            detail="Remote model configuration missing; set DOMINO_REMOTE_MODEL_HOST and DOMINO_REMOTE_MODEL_ID.",
        )

    # Build the remote URL; Domino typically serves models on HTTPS 443
    remote_url = f"https://{remote_host}:443/models/{model_id}/latest/model"

    # Build auth tuple if a token is provided; Domino model endpoints use token as both user and password
    auth = (access_token, access_token) if access_token else None

    try:
        resp = requests.post(remote_url, json={"data": request.data}, timeout=10, auth=auth)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error calling remote model: {exc}",
        )

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Remote model returned error {resp.status_code}: {resp.text}",
        )

    # Pass through the JSON response from the remote model
    try:
        return resp.json()
    except ValueError:
        # Remote model didn't return JSON
        return {"raw_response": resp.text}


@app.post("/predict", response_model=PredictionResponse)
async def predict(
    request: PredictionRequest,
    start: Optional[float] = None,
    stop: Optional[float] = None,
):
    """
    Prediction endpoint that delegates to `my_model.predict`.

    You can generate a random number like in `model.py` in two ways:

    - Request body:
      `{"data": {"start": 1, "stop": 100}}`
    - Query parameters:
      `/predict?start=1&stop=100` with an (empty) or default body.
    """
    # If query parameters are provided, prefer them (and document them clearly in Swagger)
    if start is not None and stop is not None:
        model_output = my_model.predict(start=start, stop=stop)
    else:
        # Run the model prediction using the same contract Domino uses:
        # my_model.predict(**data)
        model_output = my_model.predict(**request.data.dict())

    # Add response metadata to help identify where the response is coming from
    response_metadata = {
        "server": "uvicorn",
        "framework": "fastapi",
        "deployment_type": "domino_webapp",
        "request_received": True,
        "model_function": "my_model.predict",
    }

    return PredictionResponse(
        prediction=model_output,
        metadata=response_metadata,
    )


def detect_root_path(request: Request) -> str:
    """Detect the root path from request headers or URL."""
    # Check headers that Domino might set
    x_forwarded_prefix = request.headers.get("x-forwarded-prefix", "")
    x_script_name = request.headers.get("x-script-name", "")
    
    # Check scope for root_path (set by uvicorn)
    root_path = request.scope.get("root_path", "")
    
    # Extract from URL if we're under /apps/
    url_path = request.url.path
    if "/apps/" in url_path:
        parts = url_path.split("/")
        app_index = parts.index("apps")
        if app_index >= 0 and app_index + 1 < len(parts):
            detected = "/" + "/".join(parts[:app_index + 2])
            return detected.rstrip("/")
    
    # Return the first non-empty value found
    for path in [x_forwarded_prefix, x_script_name, root_path]:
        if path:
            return path.rstrip("/")
    
    return ""


@app.get("/info")
async def info(request: Request):
    """Get information about the deployment environment."""
    # Try to detect the base path from the request
    base_url = str(request.base_url)
    url_path = str(request.url)
    detected_path = detect_root_path(request)
    
    return {
        "framework": "FastAPI",
        "server": "uvicorn",
        "deployment": "Domino Webapp",
        "environment": {
            "DOMINO_USER": os.getenv("DOMINO_USER", "not_set"),
            "DOMINO_PROJECT_NAME": os.getenv("DOMINO_PROJECT_NAME", "not_set"),
            "DOMINO_PROJECT_OWNER": os.getenv("DOMINO_PROJECT_OWNER", "not_set"),
        },
        "request_info": {
            "base_url": base_url,
            "url": url_path,
            "path": request.url.path,
            "root_path": request.scope.get("root_path", "not_set"),
            "script_name": request.scope.get("script_name", "not_set"),
            "detected_root_path": detected_path,
        },
        "headers": {
            "x-forwarded-prefix": request.headers.get("x-forwarded-prefix", "not_present"),
            "x-script-name": request.headers.get("x-script-name", "not_present"),
        },
        "headers_expected": "Content-Type, Authorization, etc.",
        "docs_url": f"{base_url}docs",
        "openapi_url": f"{base_url}openapi.json",
        "note": "/openapi.json is now dynamically generated based on the request URL"
    }




@app.get("/debug/paths")
async def debug_paths(request: Request):
    """Debug endpoint specifically for diagnosing path issues with /docs and /openapi.json."""
    base_url = str(request.base_url).rstrip("/")
    
    # Try to determine the base path
    url_str = str(request.url)
    path = request.url.path
    
    # Extract the base path if we're under /apps/...
    base_path = ""
    if "/apps/" in path:
        # Extract everything up to and including /apps/{id}/
        parts = path.split("/")
        app_index = parts.index("apps")
        if app_index >= 0 and app_index + 1 < len(parts):
            base_path = "/" + "/".join(parts[:app_index + 2])
    
    return {
        "message": "Path debugging information for /docs and /openapi.json",
        "request_info": {
            "full_url": url_str,
            "path": path,
            "base_url": base_url,
            "detected_base_path": base_path,
            "root_path": request.scope.get("root_path", "not_set"),
            "script_name": request.scope.get("script_name", "not_set"),
        },
        "expected_urls": {
            "openapi_json": f"{base_url}/openapi.json",
            "docs": f"{base_url}/docs",
            "redoc": f"{base_url}/redoc",
        },
        "if_base_path_detected": {
            "openapi_json": f"{base_url}{base_path}/openapi.json" if base_path else "N/A",
            "docs": f"{base_url}{base_path}/docs" if base_path else "N/A",
        },
        "headers": {
            "x-forwarded-prefix": request.headers.get("x-forwarded-prefix", "not_present"),
            "x-script-name": request.headers.get("x-script-name", "not_present"),
            "host": request.headers.get("host", "not_present"),
        }
    }


@app.get("/debug/headers")
async def debug_headers(request: Request):
    """Debug endpoint to see all request headers - helps identify middleware."""
    return {
        "message": "Request headers received by FastAPI",
        "headers": dict(request.headers),
        "client_host": request.client.host if request.client else None,
        "url": str(request.url),
        "method": request.method,
        "path": request.url.path,
        "base_url": str(request.base_url),
        "root_path": request.scope.get("root_path", "not_set"),
        "script_name": request.scope.get("script_name", "not_set")
    }


@app.post("/debug/echo")
async def debug_echo(request: Request):
    """Echo back the request body and headers for debugging."""
    try:
        body = await request.body()
        body_text = body.decode('utf-8') if body else None
    except Exception as e:
        body_text = f"Error reading body: {str(e)}"
    
    return {
        "message": "Echo endpoint - returns everything we receive",
        "headers": dict(request.headers),
        "body_raw": body_text,
        "query_params": dict(request.query_params),
        "path_params": dict(request.path_params),
        "client": str(request.client) if request.client else None
    }


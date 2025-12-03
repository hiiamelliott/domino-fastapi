#!/bin/bash
# Startup script for Domino webapp deployment
# Domino webapps typically use port 8888
#
# In Domino v6.1+, you can set a custom app path like: /apps/<custom_path_name>/
# Set DOMINO_APP_PATH environment variable in Domino webapp settings

# Get port from environment variable, default to 8888 for Domino
PORT=${DOMINO_WEBAPP_PORT:-8888}
HOST=${DOMINO_WEBAPP_HOST:-0.0.0.0}

# Get the custom app path (e.g., /apps/my-fastapi-app or /apps/my-fastapi-app/)
# Default to lowercase "fastapi" to follow URL path conventions
DOMINO_APP_PATH=${DOMINO_APP_PATH:-fastapi}

echo "Starting FastAPI application..."
echo "Host: $HOST"
echo "Port: $PORT"

# Remote model configuration (for /remoteprediction endpoint)
# DOMINO_REMOTE_MODEL_HOST defaults to the current host if not provided
DOMINO_REMOTE_MODEL_HOST=${DOMINO_REMOTE_MODEL_HOST:-$DOMINO_USER_HOST}
# DOMINO_REMOTE_MODEL_ID should be set in Domino to the target model's ID (Mongo ObjectID)
DOMINO_REMOTE_MODEL_ID=${DOMINO_REMOTE_MODEL_ID:-""}
# Optional access token for the remote model
# If set, it will be used as basic auth: (token, token)
DOMINO_REMOTE_MODEL_TOKEN=${DOMINO_REMOTE_MODEL_TOKEN:-""}

export DOMINO_REMOTE_MODEL_HOST
export DOMINO_REMOTE_MODEL_ID
export DOMINO_REMOTE_MODEL_TOKEN

echo "Remote model host: ${DOMINO_REMOTE_MODEL_HOST:-not_set}"
echo "Remote model id: ${DOMINO_REMOTE_MODEL_ID:-not_set}"
if [ -n "$DOMINO_REMOTE_MODEL_TOKEN" ]; then
    echo "Remote model token: (set)"
else
    echo "Remote model token: (not set)"
fi

if [ -n "$DOMINO_APP_PATH" ]; then
    # Normalize the path (ensure it starts with / and doesn't end with /)
    ROOT_PATH=$(echo "$DOMINO_APP_PATH" | sed 's|/*$||')
    if [[ ! "$ROOT_PATH" =~ ^/ ]]; then
        ROOT_PATH="/apps/$ROOT_PATH"
    fi
    
    echo "Root Path: $ROOT_PATH"
    echo ""
    echo "Note: To customize, set DOMINO_APP_PATH environment variable in Domino webapp settings"
    echo "      Use lowercase, no spaces, URL-safe characters only (e.g., 'my-fastapi-app')"
    echo ""
    
    # Export for use in app.py
    export DOMINO_APP_PATH="$ROOT_PATH"
    
    # Run uvicorn with root_path - this ensures FastAPI generates correct URLs
    uvicorn app:app --host "$HOST" --port "$PORT" --root-path "$ROOT_PATH" --log-level info
else
    echo "Root Path: (not set)"
    echo ""
    echo "⚠️  WARNING: DOMINO_APP_PATH not set!"
    echo "   Set this environment variable in Domino webapp settings:"
    echo "   Name: DOMINO_APP_PATH"
    echo "   Value: <your-custom-path-name> (lowercase, URL-safe, e.g., 'my-fastapi-app')"
    echo ""
    echo "   This ensures /docs and /openapi.json work correctly."
    echo "   (Default: 'fastapi' will be used if not set)"
    echo ""
    
    # Run without root_path (will have issues with /docs)
    uvicorn app:app --host "$HOST" --port "$PORT" --log-level info
fi


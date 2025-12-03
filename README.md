# FastAPI Deployment in Domino

This setup allows you to deploy a FastAPI model API in Domino, even though Domino's wrapper uses Flask with uwsgi (synchronous). The solution works by:

1. Running a FastAPI/uvicorn server on localhost (separate from Flask)
2. Proxying requests from Flask to FastAPI via HTTP
3. Using monkey-patching to intercept Flask routes without modifying Domino's scripts

## Files Added

- **`fastapi_proxy.py`**: Monkey-patches Flask routes to proxy to FastAPI
- **`requirements.txt`**: Dependencies (FastAPI, uvicorn, requests)
 - **`app.py`**: FastAPI application (webapp) used behind the proxy
 - **`my_model.py`**: Domino model script that imports `fastapi_proxy` and implements `predict`

## Setup Instructions

**No modifications to Domino's core scripts needed!** However, you need to ensure `fastapi_proxy` is imported so the patching mechanism activates.

### Required Setup Step

**Import `fastapi_proxy` in your model script** (the script that contains your endpoint function):

```python
# my_model.py - This is the script you'll specify when publishing in Domino
import fastapi_proxy  # This enables FastAPI proxy

def predict(data):  # This is the function name you'll specify when publishing
    """
    Your model prediction function.
    
    Args:
        data: Input data (dict, list, or other format depending on your model)
    
    Returns:
        Prediction result
    """
    # Your model logic here
    result = your_model_function(data)
    return result
```

This is the **only modification you need to make** - add one import line to your own model script (not to any Domino-provided files).

### When Publishing in Domino

When Domino asks for the script and function:
- **Script**: The path to your model script (e.g., `my_model.py`)
- **Function**: The name of your endpoint function (e.g., `predict`)

The script you specify should have:
1. `import fastapi_proxy` at the top
2. Your endpoint function (the one you specify as the function name)

**Example**: See `my_model.py` in this project for a complete working example.

### Setup Steps

1. **Install dependencies**: Ensure `requirements.txt` dependencies are installed in your Domino environment
2. **Place files in your project**: All the FastAPI files should be in the same directory as your Domino model files
3. **Add import to your model script**: Add `import fastapi_proxy` at the top of your model script (the one referenced in `app.cfg` as `script_path`)
4. **That's it!** The patching will work automatically

### How the Auto-Patching Works

The solution uses three strategies to ensure patching works:

1. **Import Hook**: If `fastapi_proxy` is imported before `model_app`, an import hook intercepts `model_app` imports
2. **Immediate Patching**: If `model_app` is already imported when `fastapi_proxy` loads, it patches immediately
3. **Lazy Patching**: As a fallback, `make_model_app` is wrapped to patch on first call

This ensures the patching works regardless of import order, as long as `fastapi_proxy` is imported somewhere.

### Why This Works

- Your model script (with `endpoint_function`) is loaded by Domino's harness system
- By adding `import fastapi_proxy` to your script, it gets imported when your model loads
- The patching happens automatically, and Domino's `model_harness.py` and `model_app.py` remain unchanged

### Troubleshooting

Check the logs for these messages to verify patching worked:
- "FastAPI proxy: Import hook registered"
- "FastAPI proxy: Successfully patched model_app.make_model_app"
- "FastAPI proxy: Successfully lazy-patched model_app.make_model_app on first call"

If you don't see any of these messages, ensure `import fastapi_proxy` is in your model script.

## How It Works

1. **Import Time**: When `fastapi_proxy` is imported, it patches `model_app.make_model_app()` to add proxy functionality.

2. **App Creation**: When Flask app is created, the patched `make_model_app()`:
   - Creates the Flask app normally
   - Starts uvicorn in a background process on `localhost:8000`
   - Patches Flask routes to proxy requests to FastAPI

3. **Request Flow**:
   - Request comes to Flask (via uwsgi)
   - Flask route handler tries to proxy to FastAPI/uvicorn
   - If FastAPI is available, request is forwarded and response is returned
   - If FastAPI is unavailable, falls back to original Flask handler

## Configuration

You can configure the FastAPI server using environment variables:

- `FASTAPI_HOST`: Host for uvicorn (default: `127.0.0.1`)
- `FASTAPI_PORT`: Port for uvicorn (default: `8000`)

## Customizing Your FastAPI App

Edit `app.py` to implement or extend your FastAPI endpoints. The current implementation includes a `/predict` endpoint that delegates to `my_model.predict`, plus several debug endpoints for inspecting headers and paths.

## Troubleshooting

- **FastAPI server not starting**: Check that uvicorn is installed (`pip install uvicorn`)
- **Connection errors**: Ensure the port (default 8000) is not in use
- **Falling back to Flask**: The proxy will automatically fall back to Flask if FastAPI is unavailable, so your app will still work

## Notes

- The Flask wrapper remains unchanged and continues to work
- FastAPI runs as a separate process, so it has full async capabilities
- All existing Flask functionality is preserved as a fallback
- The solution is transparent to Domino's deployment system

## `/predict` endpoint and random number generation

In this project, the primary FastAPI app is defined in `app.py`, and the Domino model entrypoint is `my_model.py` with a `predict` function.

### Request/response schema

- **Request body model**: `PredictionRequest`
  - **Field**: `data` (object)
  - **Type**: `RandomNumberRequest`
    - **start**: `number` (required)
    - **stop**: `number` (required)
- **Response model**: `PredictionResponse`
  - **prediction**: arbitrary JSON (the result from `my_model.predict`)
  - **metadata**: object with deployment details (framework, server, etc.)

### Generating a random number

The `my_model.predict` function has been implemented to mirror the example in `model.py` and generate a random number between `start` and `stop`.

You can call the `/predict` endpoint in **two ways**:

1. **Using the request body (recommended for Domino calls)**:

   ```json
   {
     "data": {
       "start": 1,
       "stop": 100
     }
   }
   ```

2. **Using query parameters (convenient in Swagger UI)**:

   - URL: `/predict?start=1&stop=100`
   - Body: any valid `PredictionRequest` (the query parameters take precedence if both are present)

In both cases, the FastAPI endpoint in `app.py` delegates to:

- `my_model.predict(start=start, stop=stop)` when `start` and `stop` are provided as query parameters
- `my_model.predict(**request.data.dict())` when relying on the body payload

The `my_model.predict` implementation detects `start` and `stop`, converts them to floats, and returns a dictionary of the form:

```json
{
  "a_random_number": 42.123456
}
```

If `start`/`stop` are missing or invalid, the function falls back to the template behavior that echoes input and returns example metadata.



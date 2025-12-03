# FastAPI Deployment in Domino
By default, Domino applies a wrapper around synchronous models that uses `uwsgi`– a synchronous web server. 
However, FastAPI requires an asynchronous web server like `uvicorn`, and it is hard to configure a FastAPI-based model endpoint to receive requests in Domino.

This project demonstrates how to work around this and deploy a FastAPI-based model in Domino.

It works by:
1. Running a FastAPI/uvicorn server on localhost (separate from Flask)
2. Proxying requests from Flask to FastAPI via HTTP
3. Using monkey-patching to intercept Flask routes

## Prerequisites
**Note:** The FastAPI webapp in this project requires the new Apps architecture in Domino v6.1
In particular, it requires the deep-linking functionality, and makes use of Custom URL Endings.

## Solutions 
There are two solutions in this project:
1. A standalone model endpoint and optional FastAPI webapp. 
2. A model script built into a FastAPI webapp

## Standalone FastAPI Model Endpoint
### Setup Steps
1. **Install dependencies**: Ensure `requirements.txt` dependencies are installed in your Domino environment
2. **Add import to your model script**: Add `import fastapi_proxy` at the top of your model script
3. **That's it!** Publish your model, and the patching will work automatically

#### Import FastAPI Proxy into your model script
This is the **only modification you need to make** - add one import line to your own model script.

Add `import fastapi_proxy` to your model script (the script that contains your endpoint function):

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

#### Publish Model Endpoint in Domino
Publish your model as usual, providing the script and function:
- **Script**: The path to your model script (e.g., `my_model.py`)
- **Function**: The name of your endpoint function (e.g., `predict`)

**Example**: See `my_model.py` in this project for a complete working example.

### How This Works
1. **Import Time**: When `fastapi_proxy` is imported, it patches Domino's model endpoint wrapper, to add proxy functionality.

2. **App Creation**: When Flask app is created, the patched wrapper:
   - Creates the Flask app normally
   - Starts uvicorn in a background process on `localhost:8000`
   - Patches Flask routes to proxy requests to FastAPI

3. **Request Flow**:
   - Request comes to Flask (via uwsgi)
   - Flask route handler tries to proxy to FastAPI/uvicorn
   - If FastAPI is available, request is forwarded and response is returned
   - If FastAPI is unavailable, falls back to original Flask handler

### Why It Works
- Your model script is loaded by Domino's model wrapper
- By adding `import fastapi_proxy` to your script, it gets imported when your model loads
- The patching happens automatically, and no changes need to be made to Domino's model wrapper.

### Configuration
You can configure the FastAPI server using environment variables:
- `FASTAPI_HOST`: Host for uvicorn (default: `127.0.0.1`)
- `FASTAPI_PORT`: Port for uvicorn (default: `8000`)

However, you should not usually need to change these values.

### Troubleshooting
Check the logs for these messages to verify patching worked:
- "FastAPI proxy: Import hook registered"
- "FastAPI proxy: Successfully patched model_app.make_model_app"
- "FastAPI proxy: Successfully lazy-patched model_app.make_model_app on first call"

If you don't see any of these messages, ensure `import fastapi_proxy` is in your model script.

## FastAPI Webapp
An alternative solution is to publish a FastAPI webapp.

One of the benefits of FastAPI is its autodoc functionality. The automatically generated Swagger documentation can also be used as a tester for your model.

The sample webapp in this project has a `/predict` endpoint which can document and test a local model. In this case, it is `my_model.py`.

There is also a `/remoteprediction` endpoint that can be configured to connect to a model endpoint published elsewhere in Domino.

Edit `app.py` to modify or extend these FastAPI endpoints. 

### `/predict` endpoint and random number generation

In this project, the primary FastAPI app is defined in `app.py`, and the Domino model entrypoint is `my_model.py` with a `predict` function.

#### Generating a random number

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

2. **Using query parameters (requires deep-linking in Domino v6.1+)**:

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


### `/remoteprediction` endpoint (forwarding to a Domino model)

The app also exposes a `/remoteprediction` endpoint that forwards requests to a **separately published Domino model** (for example, a model built from `my_model.py` and deployed via the Domino Models UI).

#### Remote model URL format

Domino model endpoints have the form:

```text
https://<domino_url>:443/models/<model_id>/latest/model
```
where:

- **`<domino_url>`**: The Domino hostname (same as the webapp host).
- **`<model_id>`**: The Domino model’s ID (a Mongo ObjectID).

`app.sh` sets the following environment variables for `app.py`:

- **`DOMINO_REMOTE_MODEL_HOST`**: The Domino hostname for the remote model.
  - Defaults to `DOMINO_USER_HOST` if not explicitly set.
- **`DOMINO_REMOTE_MODEL_ID`**: The model id (`<model_id>`) for the remote model endpoint.
- **`DOMINO_REMOTE_MODEL_TOKEN`** (optional): Access token used for authenticating to the remote model.
  - If set, `/remoteprediction` uses basic auth `(token, token)` when calling the remote endpoint.
  - If not set, no auth is attached to the request.

In `app.py`, the `/remoteprediction` endpoint:

- Builds the remote URL from `DOMINO_REMOTE_MODEL_HOST` and `DOMINO_REMOTE_MODEL_ID`.
- Issues a `POST` to:

  ```text
  https://<DOMINO_REMOTE_MODEL_HOST>:443/models/<DOMINO_REMOTE_MODEL_ID>/latest/model
  ```

- Forwards the body as:

  ```json
  {
    "data": { ... }
  }
  ```

- Optionally attaches basic auth `(DOMINO_REMOTE_MODEL_TOKEN, DOMINO_REMOTE_MODEL_TOKEN)` if a token is configured.
- Returns the JSON response from the remote model directly (or raw text if the response isn’t valid JSON).

This allows your webapp to act as a lightweight proxy in front of an already-published Domino Model.

### Configuration
You can configure the FastAPI server using environment variables:

- `DOMINO_APP_PATH`: FastAPI requires an app path to find its own assets.
  - In Domino v6.1, publish the app with a custom URL ending that matches this variable. 


### Publishing the Webapp
When publishing the webapp, ensure that:
- Deep linking with query parameters is enabled
- A custom URL ending is given that matches the value of `DOMINO_APP_PATH`
  - e.g., if the app is published at `/apps/my-fastapi-app`, `DOMINO_APP_PATH="my-fastapi-app"`

## Troubleshooting
- **FastAPI server not starting**: Check that uvicorn is installed (`pip install uvicorn`)
- **Connection errors**: Ensure the port (default 8000) is not in use
- **Falling back to Flask**: The proxy will automatically fall back to Flask if FastAPI is unavailable, so your app will still work

## Files Added

- **`requirements.txt`**: Dependencies (FastAPI, uvicorn, requests)
- **`fastapi_proxy.py`**: Monkey-patches Flask routes to proxy to FastAPI
 - **`my_model.py`**: Domino model script that imports `fastapi_proxy` and implements `predict`
 - **`app.py`**: FastAPI application that documents and can test the model endpoint

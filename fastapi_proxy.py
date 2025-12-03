"""
FastAPI Proxy Module

This module intercepts the Flask app creation and adds proxy functionality
to route requests to a FastAPI/uvicorn server running on localhost.

Since Domino's model_app.py cannot be modified, this module monkey-patches
the Flask routes to proxy to FastAPI while maintaining backward compatibility.
"""
import subprocess
import threading
import time
import requests
import os
from flask import request, jsonify

# Configuration for uvicorn/FastAPI server
FASTAPI_HOST = os.environ.get("FASTAPI_HOST", "127.0.0.1")
FASTAPI_PORT = int(os.environ.get("FASTAPI_PORT", "8000"))
FASTAPI_URL = f"http://{FASTAPI_HOST}:{FASTAPI_PORT}"

# Global variable to track if uvicorn is running
_uvicorn_process = None
_uvicorn_started = False
_uvicorn_starting = False


def start_uvicorn_server():
    """Start uvicorn server in a background process."""
    global _uvicorn_process, _uvicorn_started, _uvicorn_starting
    
    if _uvicorn_started or _uvicorn_starting:
        return
    
    _uvicorn_starting = True
    
    try:
        print(f"Starting FastAPI/uvicorn server on {FASTAPI_HOST}:{FASTAPI_PORT}...")
        # Start uvicorn as a subprocess
        _uvicorn_process = subprocess.Popen(
            [
                "uvicorn",
                "fastapi_app:app",
                "--host", FASTAPI_HOST,
                "--port", str(FASTAPI_PORT),
                "--workers", "1",
                "--log-level", "info"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait a moment for server to start
        max_retries = 10
        for i in range(max_retries):
            time.sleep(0.5)
            try:
                response = requests.get(f"{FASTAPI_URL}/health", timeout=1)
                if response.status_code == 200:
                    _uvicorn_started = True
                    _uvicorn_starting = False
                    print(f"FastAPI/uvicorn server started successfully on {FASTAPI_URL}")
                    return
            except requests.exceptions.RequestException:
                continue
        
        # If we get here, server didn't start properly
        print(f"Warning: FastAPI server may not have started properly on {FASTAPI_URL}")
        print("Will attempt to use it anyway, falling back to Flask if needed")
        _uvicorn_started = True  # Allow attempts to use it
        _uvicorn_starting = False
            
    except Exception as e:
        print(f"Error starting uvicorn server: {e}")
        print("Falling back to direct Flask handling")
        _uvicorn_starting = False


def proxy_to_fastapi(path, method="GET", json_data=None):
    """Proxy a request to the FastAPI server."""
    global _uvicorn_started
    
    # Ensure uvicorn is started (non-blocking)
    if not _uvicorn_started and not _uvicorn_starting:
        threading.Thread(target=start_uvicorn_server, daemon=True).start()
        # Give it a moment
        time.sleep(0.5)
    
    try:
        url = f"{FASTAPI_URL}{path}"
        if method == "POST":
            response = requests.post(url, json=json_data, timeout=30)
        else:
            response = requests.get(url, timeout=10)
        
        return jsonify(response.json()), response.status_code
    except requests.exceptions.ConnectionError:
        # If connection fails, return None to fall back to Flask
        return None
    except Exception as e:
        print(f"Error proxying to FastAPI: {e}")
        return None


def patch_flask_app(app, config, model_app_utils):
    """
    Monkey-patch the Flask app routes to proxy to FastAPI.
    This function wraps the original route handlers.
    """
    # Find endpoints and store original handlers
    endpoints_to_patch = {}
    
    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        if rule.rule == '/model' and 'POST' in rule.methods:
            endpoints_to_patch['model'] = endpoint
        elif rule.rule == '/health' and 'GET' in rule.methods:
            endpoints_to_patch['health'] = endpoint
        elif rule.rule == '/version' and 'GET' in rule.methods:
            endpoints_to_patch['version'] = endpoint
    
    # Patch /model route
    if 'model' in endpoints_to_patch:
        endpoint = endpoints_to_patch['model']
        original_model = app.view_functions[endpoint]
        
        def patched_model():
            # Try to proxy to FastAPI first
            try:
                json_data = request.get_json() if request.is_json else None
                result = proxy_to_fastapi('/model', method='POST', json_data=json_data)
                if result is not None:
                    return result
            except Exception as e:
                print(f"Error in FastAPI proxy, falling back to Flask: {e}")
            
            # Fallback to original Flask handler
            return original_model()
        
        app.view_functions[endpoint] = patched_model
    
    # Patch /health route
    if 'health' in endpoints_to_patch:
        endpoint = endpoints_to_patch['health']
        original_health = app.view_functions[endpoint]
        
        def patched_health():
            try:
                result = proxy_to_fastapi('/health', method='GET')
                if result is not None:
                    return result
            except Exception as e:
                print(f"Error in FastAPI proxy, falling back to Flask: {e}")
            return original_health()
        
        app.view_functions[endpoint] = patched_health
    
    # Patch /version route
    if 'version' in endpoints_to_patch:
        endpoint = endpoints_to_patch['version']
        original_version = app.view_functions[endpoint]
        
        def patched_version():
            try:
                result = proxy_to_fastapi('/version', method='GET')
                if result is not None:
                    return result
            except Exception as e:
                print(f"Error in FastAPI proxy, falling back to Flask: {e}")
            return original_version()
        
        app.view_functions[endpoint] = patched_version
    
    # Start uvicorn in background
    threading.Thread(target=start_uvicorn_server, daemon=True).start()


# Monkey-patch model_app.make_model_app to add proxy functionality
def patch_make_model_app():
    """Patch the make_model_app function to add FastAPI proxy."""
    # Import here to avoid circular imports
    import model_app
    import model_app_utils
    
    # Check if already patched
    if hasattr(model_app.make_model_app, '_fastapi_patched'):
        return
    
    original_make_model_app = model_app.make_model_app
    
    def patched_make_model_app(config):
        # Create app using original function
        app = original_make_model_app(config)
        
        # Add FastAPI proxy functionality
        patch_flask_app(app, config, model_app_utils)
        
        return app
    
    # Mark as patched
    patched_make_model_app._fastapi_patched = True
    
    # Replace the function
    model_app.make_model_app = patched_make_model_app


# Use multiple strategies to ensure patching works regardless of import order
import sys
import importlib.util
import importlib.machinery


class FastAPIProxyImportHook:
    """
    Import hook that automatically patches model_app.make_model_app
    when model_app is imported, regardless of import order.
    """
    def find_spec(self, name, path, target=None):
        if name == 'model_app':
            # Find the spec for model_app
            spec = importlib.util.find_spec(name, path)
            if spec is not None and spec.loader is not None:
                # Wrap the loader to patch after module is loaded
                original_loader = spec.loader
                
                class PatchedLoader:
                    def __init__(self, original):
                        self.original = original
                    
                    def create_module(self, spec):
                        if hasattr(self.original, 'create_module'):
                            return self.original.create_module(spec)
                        return None
                    
                    def exec_module(self, module):
                        # Execute the module first
                        if hasattr(self.original, 'exec_module'):
                            self.original.exec_module(module)
                        elif hasattr(self.original, 'load_module'):
                            # For older Python versions
                            self.original.load_module(module.__name__)
                        
                        # Patch after module is loaded
                        try:
                            patch_make_model_app()
                            print("FastAPI proxy: Successfully auto-patched model_app.make_model_app via import hook")
                        except Exception as e:
                            print(f"FastAPI proxy: Warning - could not patch model_app: {e}")
                            print("Application will run in Flask-only mode.")
                
                # Replace the loader
                spec.loader = PatchedLoader(original_loader)
            return spec
        return None


# Strategy 1: Register import hook (works if fastapi_proxy is imported before model_app)
_hook_registered = False
for hook in sys.meta_path:
    if isinstance(hook, FastAPIProxyImportHook):
        _hook_registered = True
        break

if not _hook_registered:
    sys.meta_path.insert(0, FastAPIProxyImportHook())
    print("FastAPI proxy: Import hook registered - will auto-patch model_app when imported")

# Strategy 2: Patch immediately if model_app is already imported
try:
    if 'model_app' in sys.modules:
        patch_make_model_app()
        print("FastAPI proxy: Successfully patched already-imported model_app.make_model_app")
except Exception as e:
    pass  # Silent fail, will try other strategies

# Strategy 3: Lazy patching - patch make_model_app when it's first accessed
# This works even if model_app was imported before fastapi_proxy
try:
    import model_app
    if not hasattr(model_app.make_model_app, '_fastapi_patched'):
        # Store the original function
        _original_make_model_app = model_app.make_model_app
        _lazy_patch_done = False
        
        def lazy_patched_make_model_app(config):
            global _lazy_patch_done
            # Patch on first call if not already done
            if not _lazy_patch_done:
                try:
                    # Do the actual patching
                    patch_make_model_app()
                    _lazy_patch_done = True
                    print("FastAPI proxy: Successfully lazy-patched model_app.make_model_app on first call")
                except Exception as e:
                    print(f"FastAPI proxy: Warning - could not patch: {e}")
                    # If patching fails, just use original
                    return _original_make_model_app(config)
            
            # Now call the patched function (which will be model_app.make_model_app after patching)
            return model_app.make_model_app(config)
        
        model_app.make_model_app = lazy_patched_make_model_app
        print("FastAPI proxy: Set up lazy patching for model_app.make_model_app")
except (ImportError, AttributeError):
    # model_app not available yet, import hook will handle it
    pass
except Exception as e:
    print(f"FastAPI proxy: Warning - could not set up lazy patching: {e}")
    print("Application will run in Flask-only mode.")


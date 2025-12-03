"""
Package initialization to ensure fastapi_proxy is loaded.
This ensures the import hook is registered even if fastapi_proxy
isn't explicitly imported.
"""
# Import fastapi_proxy to register the import hook
try:
    import fastapi_proxy
except ImportError:
    # If fastapi_proxy can't be imported, that's okay
    # The import hook will still work if fastapi_proxy is imported later
    pass


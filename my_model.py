"""
Example Model Script for Domino FastAPI Deployment

This script demonstrates how to set up your model for FastAPI deployment in Domino.
When publishing your model in Domino, specify:
- Script: my_model.py (or the path to this file)
- Function: predict
"""
import random

import fastapi_proxy  # Required: This enables FastAPI proxy functionality

# Your model imports here
# import numpy as np
# import pandas as pd
# from your_model_library import load_model, etc.


def random_number(start, stop):
    """Generate a random number between start and stop (inclusive of range ends)."""
    return random.uniform(start, stop)


def predict(data=None, **kwargs):
    """
    Model prediction endpoint function.
    
    This function will be called by Domino's harness system.
    The FastAPI proxy will route requests through uvicorn to this function.
    
    Note: Domino calls this function with unpacked dictionary: predict(**data)
    So if you send {"data": {"key": "value"}}, it becomes predict(key="value")
    If you send {"data": {}}, it becomes predict() with no arguments
    
    Args:
        data: Input data for prediction (when passed as positional arg).
              Usually None because Domino unpacks the dict.
        **kwargs: The actual data from the request, unpacked as keyword arguments.
                 For empty data, send {"data": {}} and kwargs will be empty.
    
    Returns:
        Prediction result. Can be:
            - A dictionary: {"prediction": value, "confidence": score, ...}
            - A single value
            - Any format your API expects
    
    Examples:
        Request: {"data": {"start": 1, "stop": 100}}
        Called as: predict(start=1, stop=100)
        
        Request: {"data": {}}
        Called as: predict()
        
        Request: {"data": ""}  # This will cause an error - use {} instead!
    """
    # When Domino unpacks the data dict, it comes as kwargs
    # If data was passed positionally (shouldn't happen with Domino's setup),
    # use it instead
    if data is not None and not isinstance(data, dict):
        # Handle non-dict data passed positionally
        actual_data = data
    else:
        # Use kwargs (the unpacked dictionary)
        actual_data = kwargs if kwargs else (data if isinstance(data, dict) else {})

    # If we receive "start" and "stop" keys, behave like model.py and
    # return a random number in that range.
    if isinstance(actual_data, dict) and "start" in actual_data and "stop" in actual_data:
        start = actual_data["start"]
        stop = actual_data["stop"]
        # Allow ints, floats, or strings that can be cast to float
        try:
            start_val = float(start)
            stop_val = float(stop)
        except (TypeError, ValueError):
            # Fall back to template behavior if inputs are invalid
            pass
        else:
            return {"a_random_number": random_number(start_val, stop_val)}
    
    # Handle empty data case
    if not actual_data or (isinstance(actual_data, dict) and len(actual_data) == 0):
        # Empty data - return appropriate response
        result = {
            "prediction": "example_result",
            "input_received": {},
            "message": "Empty data received - replace with your actual model logic"
        }
        return result
    
    # Example: Simple echo/passthrough (replace with your actual model logic)
    if isinstance(data, dict):
        # Handle dictionary input
        result = {
            "prediction": "example_result",
            "input_received": data,
            "message": "This is a template - replace with your actual model logic"
        }
    elif isinstance(data, list):
        # Handle list input
        result = {
            "prediction": "example_result",
            "input_received": data,
            "message": "This is a template - replace with your actual model logic"
        }
    else:
        # Handle other input types
        result = {
            "prediction": "example_result",
            "input_received": str(data),
            "message": "This is a template - replace with your actual model logic"
        }

    return result


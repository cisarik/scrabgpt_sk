from google.genai import types
import inspect

print("Inspecting google.genai.types...")

# Check for ThinkingConfig
if hasattr(types, "ThinkingConfig"):
    print("Found ThinkingConfig")
    print(inspect.signature(types.ThinkingConfig))
else:
    print("ThinkingConfig NOT found")

# Check GenerateContentConfig fields
print("\nGenerateContentConfig fields:")
try:
    # It might be a Pydantic model or similar
    if hasattr(types.GenerateContentConfig, "model_fields"):
        for name in types.GenerateContentConfig.model_fields:
            print(f"- {name}")
    else:
        # Try to inspect __init__
        sig = inspect.signature(types.GenerateContentConfig)
        for name in sig.parameters:
            print(f"- {name}")
except Exception as e:
    print(f"Could not inspect GenerateContentConfig: {e}")

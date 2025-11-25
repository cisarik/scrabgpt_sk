import asyncio
import os
import sys
import json

# Add project root to path
sys.path.append(os.getcwd())

from google import genai

async def main():
    print("Listing Vertex AI models...")
    
    # Load credentials
    creds_path = os.path.abspath("vertexaccount.json")
    project_id = "vertexaccount"
    if os.path.exists(creds_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        try:
            with open(creds_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                project_id = data.get("project_id", project_id)
        except Exception:
            pass
            
    print(f"Project ID: {project_id}")
    
    # List models in us-central1
    print("\n--- Listing models in us-central1 ---")
    try:
        client = genai.Client(vertexai=True, project=project_id, location="us-central1")
        # The SDK might have a list method. Let's try to iterate.
        # Based on google-genai docs (if I recall correctly or guessing standard pattern)
        # It might be client.models.list()
        
        try:
            for model in client.models.list():
                print(f"Model: {model.name} (ID: {model.name.split('/')[-1]})")
        except Exception as e:
            print(f"Failed to list models: {e}")
            # Fallback to trying specific names if list fails
            
    except Exception as e:
        print(f"Client init failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())

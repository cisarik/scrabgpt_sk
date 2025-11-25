import asyncio
import os
import sys
import json
from google import genai
from google.genai import types

async def main():
    print("Verifying Gemini 3 call with ThinkingConfig...")
    
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
    
    try:
        client = genai.Client(vertexai=True, project=project_id, location="us-central1")
        
        print("Calling gemini-3-pro-preview with thinking_config...")
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(include_thoughts=True)
        )
        
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents="Hello",
            config=config
        )
        print("SUCCESS!")
        print(f"Response text: {response.text}")
        
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(main())

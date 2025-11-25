import os
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load .env
load_dotenv(override=True)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath("vertexaccount.json")

async def test_generate():
    project_id = "vertexaccount"
    try:
        import json
        with open("vertexaccount.json", "r") as f:
            creds = json.load(f)
            project_id = creds.get("project_id", project_id)
    except:
        pass
        
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    print(f"Testing generate for project: {project_id} in {location}")
    
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location=location
    )
    
    model_id = "gemini-2.5-pro"
    print(f"Model: {model_id}")
    
    try:
        config = types.GenerateContentConfig(
            max_output_tokens=100,
            temperature=0.7,
            thinking_config=types.ThinkingConfig(include_thoughts=True)
        )
        
        response = client.models.generate_content(
            model=model_id,
            contents=[types.Content(role="user", parts=[types.Part(text="Hello")])],
            config=config
        )
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_generate())

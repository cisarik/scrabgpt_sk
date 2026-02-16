import os
import asyncio
from dotenv import load_dotenv
from google import genai

# Load .env
load_dotenv(override=True)

# Set credentials explicitly
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath("vertexaccount.json")

async def list_vertex_models():
    project_id = "vertexaccount" # Default fallback
    # Try to parse project_id from credentials file if exists
    try:
        import json
        with open("vertexaccount.json", "r") as f:
            creds = json.load(f)
            project_id = creds.get("project_id", project_id)
    except Exception:
        pass
        
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    print(f"Listing models for project: {project_id} in {location}")
    
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location=location
    )
    
    try:
        # Sync call in this library version? Or async? 
        # The VertexClient in app wraps it in asyncio.to_thread, suggesting it's sync.
        # But google-genai usually has .models.list()
        
        pager = client.models.list()
        print("Available models:")
        found = False
        for model in pager:
            # Filter for gemini
            if "gemini" in model.name:
                print(f" - {model.name} (display: {model.display_name})")
                found = True
        
        if not found:
            print("No Gemini models found.")
            
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    asyncio.run(list_vertex_models())

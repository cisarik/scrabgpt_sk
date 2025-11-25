import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from scrabgpt.ai.vertex import VertexClient

async def main():
    print("Initializing VertexClient...")
    try:
        client = VertexClient(project_id="test-project", location="europe-west1")
        print("VertexClient initialized successfully.")
        
        # Check call_model signature
        import inspect
        sig = inspect.signature(client.call_model)
        print(f"call_model signature: {sig}")
        
        # Verify it has required parameters
        params = sig.parameters
        assert "model_id" in params
        assert "prompt" in params
        assert "messages" in params
        assert "max_tokens" in params
        
        print("Interface verification passed.")
        
    except Exception as e:
        print(f"Verification failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

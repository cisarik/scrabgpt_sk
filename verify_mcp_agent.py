import asyncio
import os
import sys
import logging
from google.genai import types

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("verify_mcp")

async def main():
    print("Verifying MCP Agent...")
    
    # Import after path setup if needed, but we are in root
    from scrabgpt.ai.vertex import VertexClient
    from scrabgpt.ai.mcp_adapter import get_gemini_tools
    
    # Initialize client
    client = VertexClient(location="us-central1")
    
    # Get tools
    tools = get_gemini_tools()
    print(f"Loaded {len(tools[0].function_declarations)} tools")
    
    # Test prompt that requires tool use
    prompt = "What is the current state of the board? Use the get_board_state tool."
    
    print(f"Prompt: {prompt}")
    
    try:
        response = await client.call_model(
            model_id="gemini-2.5-pro",
            prompt=prompt,
            tools=tools,
            thinking_mode=False
        )
        
        print("\nResponse:")
        print(response.get("content"))
        
        # Check logs to see if tool was executed (we can't easily check internal logs here, 
        # but the output should reflect the tool result)
        
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

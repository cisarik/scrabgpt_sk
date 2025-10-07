"""Example: Using ScrabGPT MCP Server with mcp-use and LangChain.

This script demonstrates how to:
1. Connect to the ScrabGPT MCP server
2. Create an AI agent with access to Scrabble game logic tools
3. Query the agent to validate moves and calculate scores

Requirements:
    - OPENAI_API_KEY in .env
    - mcp-use, langchain-openai installed (already in pyproject.toml)

Usage:
    poetry run python examples/mcp_agent_demo.py
"""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

# Load environment
load_dotenv()


async def demo_basic_query():
    """Demo: Basic query to MCP agent about Scrabble rules."""
    print("=" * 80)
    print("DEMO 1: Basic Scrabble Rules Query")
    print("=" * 80)
    
    # Load MCP server configuration
    config_path = Path(__file__).parent.parent / "scrabble_mcp.json"
    with open(config_path) as f:
        config = json.load(f)
    
    # Create MCP client
    print("\n1. Connecting to ScrabGPT MCP server...")
    client = MCPClient.from_dict(config)
    
    # Create LLM
    print("2. Creating OpenAI LLM (gpt-4o)...")
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # Create agent with MCP tools
    print("3. Creating MCP agent with ScrabGPT tools...")
    agent = MCPAgent(
        llm=llm,
        client=client,
        max_steps=10,
        verbose=True,
    )
    
    # Query the agent
    query = "What tile values are available in the Slovak variant?"
    print(f"\n4. Querying agent: '{query}'")
    print("-" * 80)
    
    result = await agent.run(query)
    
    print("\n5. Agent Response:")
    print("-" * 80)
    print(result)
    print()


async def demo_move_validation():
    """Demo: Validate a Scrabble move using MCP tools."""
    print("=" * 80)
    print("DEMO 2: Move Validation")
    print("=" * 80)
    
    config_path = Path(__file__).parent.parent / "scrabble_mcp.json"
    with open(config_path) as f:
        config = json.load(f)
    
    client = MCPClient.from_dict(config)
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    agent = MCPAgent(llm=llm, client=client, max_steps=20, verbose=True)
    
    # Define a first move scenario
    query = """
I want to play the word "CAT" horizontally starting at position (7, 6) 
on an empty Scrabble board. The placements are:
- (7, 6): C
- (7, 7): A  (center square)
- (7, 8): T

Is this a legal first move? Please validate using the available tools.
"""
    
    print(f"Query: {query}")
    print("-" * 80)
    
    result = await agent.run(query)
    
    print("\nAgent Response:")
    print("-" * 80)
    print(result)
    print()


async def demo_score_calculation():
    """Demo: Calculate score for a move."""
    print("=" * 80)
    print("DEMO 3: Score Calculation")
    print("=" * 80)
    
    config_path = Path(__file__).parent.parent / "scrabble_mcp.json"
    with open(config_path) as f:
        config = json.load(f)
    
    client = MCPClient.from_dict(config)
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    agent = MCPAgent(llm=llm, client=client, max_steps=20, verbose=True)
    
    query = """
On an empty board, I play "CATS" horizontally starting at (7, 6):
- (7, 6): C
- (7, 7): A  (center square - double word score)
- (7, 8): T
- (7, 9): S

Calculate the score for this move. Use Slovak tile values and 
consider that the center square provides a double word score.
"""
    
    print(f"Query: {query}")
    print("-" * 80)
    
    result = await agent.run(query)
    
    print("\nAgent Response:")
    print("-" * 80)
    print(result)
    print()


async def demo_direct_tool_calls():
    """Demo: Direct tool calls without agent (lower-level API)."""
    print("=" * 80)
    print("DEMO 4: Direct Tool Calls (No Agent)")
    print("=" * 80)
    
    config_path = Path(__file__).parent.parent / "scrabble_mcp.json"
    with open(config_path) as f:
        config = json.load(f)
    
    client = MCPClient.from_dict(config)
    
    # List available tools
    print("\n1. Listing available tools...")
    tools = await client.list_tools()
    print(f"   Found {len(tools)} tools:")
    for tool in tools[:5]:  # Show first 5
        print(f"   - {tool.name}: {tool.description}")
    print(f"   ... and {len(tools) - 5} more")
    
    # Call a specific tool
    print("\n2. Calling 'get_tile_values' tool directly...")
    result = await client.call_tool(
        server_name="scrabble",
        tool_name="get_tile_values",
        arguments={"variant": "slovak"},
    )
    
    print("   Result:")
    print("   " + result[0].text[:200] + "...")
    print()


async def main():
    """Run all demos."""
    print("\n🎮 ScrabGPT MCP Server Demo\n")
    
    try:
        # Run demos
        await demo_basic_query()
        input("\nPress Enter to continue to next demo...")
        
        await demo_move_validation()
        input("\nPress Enter to continue to next demo...")
        
        await demo_score_calculation()
        input("\nPress Enter to continue to next demo...")
        
        await demo_direct_tool_calls()
        
        print("\n✅ All demos completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

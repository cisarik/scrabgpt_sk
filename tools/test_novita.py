#!/usr/bin/env python3
"""Quick test script for Novita integration.

Usage:
    poetry run python tools/test_novita.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrabgpt.ai.novita import NovitaClient


async def main():
    """Test Novita client."""
    api_key = os.getenv("NOVITA_API_KEY")
    
    if not api_key:
        print("❌ NOVITA_API_KEY not set in environment")
        print("   Add it to .env file:")
        print("   NOVITA_API_KEY='your-key-here'")
        return 1
    
    print(f"✓ API key found: {api_key[:20]}...")
    print()
    
    # Test 1: Fetch models
    print("=" * 60)
    print("TEST 1: Fetching available models")
    print("=" * 60)
    
    client = NovitaClient(api_key)
    
    try:
        models = await client.fetch_models()
        print(f"✓ Fetched {len(models)} models")
        print()
        
        if not models:
            print("❌ No models returned!")
            return 1
        
        # Group by category
        categories = {}
        for model in models:
            cat = model.get("category", "other")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(model)
        
        print("Models by category:")
        for cat, cat_models in sorted(categories.items()):
            print(f"\n  {cat.upper()} ({len(cat_models)} models):")
            for model in cat_models[:3]:  # Show first 3 per category
                print(f"    - {model['id']}")
                print(f"      Name: {model['name']}")
                print(f"      Context: {model['context_length']:,} tokens")
            if len(cat_models) > 3:
                print(f"    ... and {len(cat_models) - 3} more")
        
        print()
        print("=" * 60)
        print("TEST 2: Call a model")
        print("=" * 60)
        
        # Pick first model
        test_model = models[0]
        print(f"Testing with: {test_model['id']}")
        print()
        
        prompt = "Please respond with valid JSON: {\"test\": \"hello\", \"number\": 42}"
        
        result = await client.call_model(
            test_model['id'],
            prompt,
            max_tokens=100,
        )
        
        print(f"Status: {result.get('status')}")
        
        if result.get('status') == 'ok':
            print("✓ Model responded successfully")
            content = result.get('content', '')
            print(f"Content (first 200 chars): {content[:200]}")
            
            reasoning = result.get('reasoning_content', '')
            if reasoning:
                print(f"Reasoning (first 200 chars): {reasoning[:200]}")
            
            print(f"Tokens: prompt={result.get('prompt_tokens')}, completion={result.get('completion_tokens')}")
        else:
            print(f"❌ Model call failed: {result.get('error')}")
            return 1
        
        print()
        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Start ScrabGPT: poetry run scrabgpt")
        print("2. Go to Settings → AI Protivník")
        print("3. Select 'Novita AI' mode")
        print("4. Click 'Nastaviť' button")
        print("5. Select models and click OK")
        print("6. Start a new game and watch the results table!")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

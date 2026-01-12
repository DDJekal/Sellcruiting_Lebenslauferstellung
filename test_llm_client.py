"""Quick test for LLMClient with Claude/OpenAI."""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from llm_client import LLMClient


def test_llm_client():
    """Test LLM client with simple prompt."""
    print("\n" + "="*60)
    print("TESTING LLM CLIENT")
    print("="*60)
    
    # Check API keys
    has_anthropic = os.getenv("ANTHROPIC_API_KEY") is not None
    has_openai = os.getenv("OPENAI_API_KEY") is not None
    
    print(f"\nConfiguration:")
    print(f"   ANTHROPIC_API_KEY: {'[SET]' if has_anthropic else '[MISSING]'}")
    print(f"   OPENAI_API_KEY: {'[SET]' if has_openai else '[MISSING]'}")
    
    if not has_openai and not has_anthropic:
        print("\nERROR: No API keys configured!")
        return
    
    # Initialize client
    print(f"\nInitializing LLMClient...")
    client = LLMClient(prefer_claude=True)
    
    # Test prompt
    system_prompt = """Du bist ein JSON-Generator. 
Antworte IMMER nur mit validem JSON, ohne zusaetzlichen Text.
"""
    
    user_prompt = """Erstelle ein JSON-Objekt mit folgenden Feldern:
- name: "Test User"
- age: 30
- city: "Berlin"

Antworte nur mit dem JSON, nichts anderes."""
    
    print(f"\nSending test request...")
    print(f"   System: {system_prompt[:50]}...")
    print(f"   User: {user_prompt[:50]}...")
    
    try:
        response = client.create_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0,
            max_tokens=200
        )
        
        print(f"\nSUCCESS!")
        print(f"   Response length: {len(response)} characters")
        print(f"\nResponse:")
        print(f"   {response}")
        
        # Try to parse JSON
        import json
        parsed = json.loads(response)
        print(f"\nValid JSON!")
        print(f"   Keys: {list(parsed.keys())}")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("Test complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_llm_client()

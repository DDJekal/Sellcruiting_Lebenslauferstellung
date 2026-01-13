"""Unified LLM client with Claude primary + OpenAI fallback."""
import os
import json
from typing import Dict, Any, List, Optional
from openai import OpenAI
from anthropic import Anthropic


class LLMClient:
    """
    Hybrid LLM client: Claude Sonnet 4.5 primary, GPT-4o fallback.
    
    Output-Struktur ist identisch (JSON), nur API-Calls unterschiedlich.
    """
    
    def __init__(self, prefer_claude: bool = True):
        """
        Initialize with both clients.
        
        Args:
            prefer_claude: If True, try Claude first, fallback to OpenAI
        """
        self.prefer_claude = prefer_claude and os.getenv("ANTHROPIC_API_KEY") is not None
        
        # Initialize OpenAI client (always needed as fallback)
        self.openai_client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Initialize Anthropic client (optional)
        self.anthropic_client = None
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                self.anthropic_client = Anthropic(
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
            except Exception as e:
                print(f"   [WARN] Could not initialize Anthropic client: {e}")
                self.prefer_claude = False
        
        # Model configs
        self.claude_model = "claude-sonnet-4-20250514"
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")
    
    def create_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0,
        max_tokens: int = 4000
    ) -> str:
        """
        Create completion with automatic fallback.
        
        Args:
            system_prompt: System instructions
            user_prompt: User query/context
            temperature: Sampling temperature (0 = deterministic)
            max_tokens: Maximum tokens in response
        
        Returns:
            JSON string (identical structure regardless of provider)
        """
        
        # Try Claude first (if available and preferred)
        if self.prefer_claude and self.anthropic_client:
            try:
                response = self._call_claude(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                print("   [LLM] Claude Sonnet 4.5 OK")
                return response
            except Exception as e:
                print(f"   [WARN] Claude failed: {e}")
                print(f"   [LLM] Falling back to OpenAI...")
        
        # Fallback to OpenAI (or primary if Claude not available)
        try:
            response = self._call_openai(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            provider = "GPT-4o (fallback)" if self.prefer_claude else "GPT-4o"
            print(f"   [LLM] OpenAI {provider} OK")
            return response
        except Exception as e:
            raise Exception(f"LLM call failed: {e}")
    
    def _call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """Call Claude API."""
        response = self.anthropic_client.messages.create(
            model=self.claude_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # Extract text from response
        response_text = response.content[0].text
        
        # Claude sometimes wraps JSON in code blocks - remove them
        response_text = response_text.strip()
        if response_text.startswith("```"):
            # Remove ```json or ``` at start
            lines = response_text.split("\n")
            lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            response_text = "\n".join(lines).strip()
        
        # Claude sometimes adds explanation after JSON - extract only JSON
        # Find the first { and last }
        try:
            start_idx = response_text.index("{")
            # Find matching closing brace
            brace_count = 0
            end_idx = -1
            for i in range(start_idx, len(response_text)):
                if response_text[i] == "{":
                    brace_count += 1
                elif response_text[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > start_idx:
                response_text = response_text[start_idx:end_idx]
        except ValueError:
            # No { found, return as is
            pass
        
        return response_text
    
    def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """Call OpenAI API."""
        response = self.openai_client.chat.completions.create(
            model=self.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content

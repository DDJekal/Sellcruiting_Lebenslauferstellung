"""Type enricher for inferring prompt types (Shadow-Types)."""
import re
import hashlib
from typing import Dict, List, Any
import os
from openai import OpenAI

from models import ShadowType, PromptType, MandantenConfig


class TypeEnricher:
    """Infers prompt types using heuristics + LLM fallback."""
    
    def __init__(self, api_key: str = None):
        """Initialize with OpenAI API key."""
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.cache: Dict[str, ShadowType] = {}
    
    def infer_types(self, protocol: Dict[str, Any], mandanten_config: MandantenConfig) -> Dict[int, ShadowType]:
        """Infer types for all prompts in protocol."""
        shadow_types = {}
        unsure_prompts = []
        
        for page in protocol["pages"]:
            page_name = page["name"]
            
            for prompt in page["prompts"]:
                # Check if explicit type exists in protocol (NEW)
                explicit_type = prompt.get("type")
                if explicit_type:
                    try:
                        prompt_type = PromptType(explicit_type)
                        shadow_types[prompt["id"]] = ShadowType(
                            prompt_id=prompt["id"],
                            inferred_type=prompt_type,
                            confidence=1.0,
                            reasoning=f"Explicit type from protocol: {explicit_type}"
                        )
                        continue  # Skip heuristics and LLM
                    except ValueError:
                        # Invalid type value, fall back to heuristics
                        pass
                
                # Check cache first
                cache_key = self._get_cache_key(prompt)
                if cache_key in self.cache:
                    shadow_types[prompt["id"]] = self.cache[cache_key]
                    continue
                
                # Try heuristics
                heuristic_result = self._apply_heuristics(
                    prompt, page_name, mandanten_config
                )
                
                if heuristic_result and heuristic_result.confidence >= 0.9:
                    shadow_types[prompt["id"]] = heuristic_result
                    self.cache[cache_key] = heuristic_result
                else:
                    # Mark for LLM classification
                    unsure_prompts.append((prompt, page_name))
        
        # Batch classify unsure prompts via LLM
        if unsure_prompts:
            llm_results = self._llm_classify_batch(unsure_prompts)
            for prompt_id, shadow_type in llm_results.items():
                shadow_types[prompt_id] = shadow_type
                # Cache it
                cache_key = self._get_cache_key({"id": prompt_id, "question": shadow_type.reasoning})
                self.cache[cache_key] = shadow_type
        
        return shadow_types
    
    def _get_cache_key(self, prompt: Dict[str, Any]) -> str:
        """Generate cache key for prompt."""
        text = f"{prompt['id']}_{prompt['question']}"
        return hashlib.md5(text.encode()).hexdigest()
    
    def _apply_heuristics(
        self,
        prompt: Dict[str, Any],
        page_name: str,
        mandanten_config: MandantenConfig
    ) -> ShadowType:
        """Apply heuristic rules to infer prompt type."""
        question = prompt["question"]
        q_lower = question.lower()
        
        # Page-based fallback (info pages)
        if page_name in mandanten_config.info_page_names:
            if "!!!" in question or "bitte unbedingt erwähnen" in q_lower:
                return ShadowType(
                    prompt_id=prompt["id"],
                    inferred_type=PromptType.RECRUITER_INSTRUCTION,
                    confidence=0.98,
                    reasoning="Recruiter instruction (contains !!!)"
                )
            return ShadowType(
                prompt_id=prompt["id"],
                inferred_type=PromptType.INFO,
                confidence=0.94,
                reasoning="Info page"
            )
        
        # Mandanten-specific heuristics
        for rule in mandanten_config.heuristic_rules:
            if re.search(rule.pattern, q_lower, re.IGNORECASE):
                return ShadowType(
                    prompt_id=prompt["id"],
                    inferred_type=rule.type,
                    confidence=rule.confidence,
                    reasoning=f"Matched pattern: {rule.pattern}"
                )
        
        # General heuristics
        if q_lower.startswith("zwingend:") or q_lower.startswith("wünschenswert:"):
            return ShadowType(
                prompt_id=prompt["id"],
                inferred_type=PromptType.YES_NO,
                confidence=0.92,
                reasoning="Starts with 'Zwingend:' or 'Wünschenswert:'"
            )
        
        # If no heuristic matched
        return None
    
    def _llm_classify_batch(
        self, prompts_with_pages: List[tuple]
    ) -> Dict[int, ShadowType]:
        """Classify prompts using LLM (batch)."""
        results = {}
        
        # Prepare prompts for LLM
        prompts_data = [
            {"id": prompt["id"], "question": prompt["question"], "page_name": page_name}
            for prompt, page_name in prompts_with_pages
        ]
        
        system_prompt = """Du klassifizierst deutschsprachige Fragen aus einem Gesprächsprotokoll.
Gib NUR JSON zurück. Keine Erklärungen.

Verfügbare Labels:
- yes_no: Ja/Nein-Frage
- yes_no_with_details: Ja/Nein mit Details
- text: Freitext
- text_list: Liste von Texten
- number: Zahl
- date: Datum
- routing_rule: Routing-Entscheidung
- info: Nur Anzeige, keine Eingabe

Für jede Frage gib zurück:
{"prompt_id": <int>, "inferred_type": "<label>", "confidence": <0-1>, "reasoning": "..."}"""
        
        user_prompt = f"Klassifiziere diese Prompts:\n{prompts_data}"
        
        try:
            response = self.client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0
            )
            
            # Parse response
            import json
            classifications = json.loads(response.choices[0].message.content)
            
            # Handle both array and object responses
            if isinstance(classifications, dict) and "prompts" in classifications:
                classifications = classifications["prompts"]
            elif isinstance(classifications, dict):
                classifications = [classifications]
            
            for item in classifications:
                results[item["prompt_id"]] = ShadowType(
                    prompt_id=item["prompt_id"],
                    inferred_type=PromptType(item["inferred_type"]),
                    confidence=item.get("confidence", 0.8),
                    reasoning=item.get("reasoning", "LLM classification")
                )
        
        except Exception as e:
            print(f"Warning: LLM classification failed: {e}")
            # Fallback to safe defaults
            for prompt, page_name in prompts_with_pages:
                results[prompt["id"]] = ShadowType(
                    prompt_id=prompt["id"],
                    inferred_type=PromptType.TEXT,
                    confidence=0.5,
                    reasoning=f"Fallback due to error: {e}"
                )
        
        return results


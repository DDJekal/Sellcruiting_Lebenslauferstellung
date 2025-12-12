"""Mapper for mapping extracted answers to protocol structure."""
from typing import Dict, Any, List

from models import (
    ShadowType, PromptAnswer, FilledPrompt, FilledPage, FilledProtocol, PromptType
)


class Mapper:
    """Maps extracted answers to filled protocol structure."""
    
    def map_answers(
        self,
        protocol: Dict[str, Any],
        shadow_types: Dict[int, ShadowType],
        extracted_answers: Dict[int, PromptAnswer]
    ) -> FilledProtocol:
        """Map answers to filled protocol structure."""
        
        filled_pages = []
        
        for page in protocol["pages"]:
            filled_prompts = []
            
            for prompt in page["prompts"]:
                prompt_id = prompt["id"]
                shadow_type = shadow_types.get(prompt_id)
                
                if not shadow_type:
                    # Prompt has no shadow type (shouldn't happen, but handle gracefully)
                    # Create a default one
                    shadow_type = ShadowType(
                        prompt_id=prompt_id,
                        inferred_type=PromptType.TEXT,
                        confidence=0.0,
                        reasoning="No shadow type found"
                    )
                
                # Get answer (may be None for info prompts)
                answer = extracted_answers.get(
                    prompt_id,
                    PromptAnswer(checked=None, value=None, confidence=0.0, evidence=[], notes="Nicht befüllt")
                )
                
                # For yes_no prompts: set value to "ja"/"nein" based on checked
                if shadow_type.inferred_type == PromptType.YES_NO:
                    if answer.checked is True:
                        answer.value = "ja"
                    elif answer.checked is False:
                        answer.value = "nein"
                    elif answer.checked is None:
                        answer.value = None  # Keep null for "nicht erwähnt"
                
                # For yes_no_with_details: prepend "ja"/"nein" to details
                elif shadow_type.inferred_type == PromptType.YES_NO_WITH_DETAILS:
                    if answer.checked is True:
                        # Prepend "ja" to existing details
                        if answer.value:
                            answer.value = f"ja ({answer.value})"
                        else:
                            answer.value = "ja"
                    elif answer.checked is False:
                        if answer.value:
                            answer.value = f"nein ({answer.value})"
                        else:
                            answer.value = "nein"
                    # If null, keep value as is (might be None or empty)
                
                filled_prompt = FilledPrompt(
                    id=prompt_id,
                    question=prompt["question"],
                    inferred_type=shadow_type.inferred_type,
                    answer=answer
                )
                
                filled_prompts.append(filled_prompt)
            
            filled_page = FilledPage(
                id=page["id"],
                name=page["name"],
                prompts=filled_prompts
            )
            filled_pages.append(filled_page)
        
        return FilledProtocol(
            protocol_id=protocol["id"],
            protocol_name=protocol["name"],
            pages=filled_pages,
            extracted_extras={}
        )


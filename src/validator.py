"""Validator for checking must-criteria and applying routing rules."""
from typing import List, Dict, Any

from .models import FilledProtocol, MandantenConfig, PromptAnswer, Evidence


class Validator:
    """Validates filled protocol and applies routing rules."""
    
    def apply_implicit_defaults(
        self,
        filled_protocol: FilledProtocol,
        mandanten_config: MandantenConfig
    ) -> FilledProtocol:
        """Apply implicit defaults for prompts that were not explicitly mentioned."""
        
        # Build prompt lookup
        prompts_by_id = {}
        for page in filled_protocol.pages:
            for prompt in page.prompts:
                prompts_by_id[prompt.id] = prompt
        
        # Apply each implicit default rule
        for implicit_default in mandanten_config.implicit_defaults:
            target_prompt = prompts_by_id.get(implicit_default.prompt_id)
            
            if not target_prompt:
                continue
            
            # Only apply if prompt was not filled (checked=null AND no evidence)
            if target_prompt.answer.checked is None and not target_prompt.answer.evidence:
                # Apply default answer
                default = implicit_default.default_answer
                target_prompt.answer.checked = default.checked
                target_prompt.answer.value = default.value
                target_prompt.answer.confidence = default.confidence
                target_prompt.answer.notes = default.notes
        
        return filled_protocol
    
    def validate_must_criteria(
        self,
        filled_protocol: FilledProtocol,
        mandanten_config: MandantenConfig
    ) -> List[str]:
        """Validate must-have criteria. Returns list of errors."""
        errors = []
        
        # Build prompt lookup
        prompts_by_id = {}
        for page in filled_protocol.pages:
            for prompt in page.prompts:
                prompts_by_id[prompt.id] = prompt
        
        # Check each must criterion
        for criterion in mandanten_config.must_criteria:
            prompt = prompts_by_id.get(criterion.prompt_id)
            
            if not prompt:
                errors.append(f"Prompt {criterion.prompt_id} nicht gefunden")
                continue
            
            if prompt.answer.checked != criterion.expected:
                errors.append(criterion.error_msg)
        
        return errors
    
    def apply_routing_rules(
        self,
        filled_protocol: FilledProtocol,
        mandanten_config: MandantenConfig
    ) -> FilledProtocol:
        """Apply routing rules to automatically fill certain prompts."""
        
        # Build prompt lookup
        prompts_by_id = {}
        for page in filled_protocol.pages:
            for prompt in page.prompts:
                prompts_by_id[prompt.id] = prompt
        
        # Apply each routing rule
        for rule in mandanten_config.routing_rules:
            # Check if all conditions are met
            conditions_met = True
            
            for condition in rule.conditions:
                source_prompt = prompts_by_id.get(condition.prompt)
                
                if not source_prompt:
                    conditions_met = False
                    break
                
                # Get the field value
                if condition.field == "checked":
                    field_value = source_prompt.answer.checked
                elif condition.field == "value":
                    field_value = source_prompt.answer.value
                else:
                    conditions_met = False
                    break
                
                # Evaluate condition
                if not self._evaluate_condition(field_value, condition.operator, condition.value):
                    conditions_met = False
                    break
            
            # If all conditions met, apply action
            if conditions_met:
                target_prompt = prompts_by_id.get(rule.target_prompt)
                if target_prompt:
                    # Apply action
                    if rule.action.checked is not None:
                        target_prompt.answer.checked = rule.action.checked
                    if rule.action.value is not None:
                        target_prompt.answer.value = rule.action.value
                    if rule.action.notes is not None:
                        target_prompt.answer.notes = rule.action.notes
                    
                    # Set confidence to 1.0 (automatic)
                    target_prompt.answer.confidence = 1.0
        
        return filled_protocol
    
    def _evaluate_condition(self, field_value: Any, operator: str, expected_value: Any) -> bool:
        """Evaluate a single condition."""
        if operator == "==":
            return field_value == expected_value
        elif operator == "!=":
            return field_value != expected_value
        elif operator == "contains":
            if isinstance(field_value, list):
                return any(expected_value.lower() in str(item).lower() for item in field_value)
            return expected_value.lower() in str(field_value).lower()
        elif operator == "not_contains":
            if isinstance(field_value, list):
                return not any(expected_value.lower() in str(item).lower() for item in field_value)
            if field_value is None:
                return True
            return expected_value.lower() not in str(field_value).lower()
        else:
            return False


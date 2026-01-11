"""Validator for checking must-criteria and applying routing rules."""
from typing import List, Dict, Any

from models import FilledProtocol, MandantenConfig, PromptAnswer, Evidence


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
    
    def evaluate_qualification(
        self,
        filled_protocol: FilledProtocol,
        mandanten_config: MandantenConfig
    ) -> Dict[str, Any]:
        """
        Evaluate if applicant is qualified based on must-criteria and qualification groups.
        
        ROBUSTE LOGIK:
        - Prüft qualification_groups mit OR/AND-Logik (Priorität 1)
        - Fallback zu must_criteria (legacy, Priorität 2)
        - Fallback zu impliziter Qualifikationserkennung (Priorität 3)
        
        Returns:
            Dict with qualification status, summary text, and details
        """
        # Build prompt lookup for additional analysis
        prompts_by_id = {}
        for page in filled_protocol.pages:
            for prompt in page.prompts:
                prompts_by_id[prompt.id] = prompt
        
        errors = []
        fulfilled_count = 0
        total_count = 0
        evaluation_method = None
        group_evaluations = []
        
        # 1. PRIORITÄT: Qualification Groups (neue flexible Struktur)
        if mandanten_config.qualification_groups:
            evaluation_method = "qualification_groups"
            
            for group in mandanten_config.qualification_groups:
                fulfilled_options = []
                total_options = len(group.options)
                
                # Evaluiere jede Option in der Gruppe
                for option in group.options:
                    prompt = prompts_by_id.get(option.prompt_id)
                    
                    if not prompt:
                        continue
                    
                    # Option ist erfüllt wenn:
                    # - checked=True ODER
                    # - value ist gesetzt UND confidence >= 0.7 UND hat Evidence
                    is_fulfilled = (
                        prompt.answer.checked == True or
                        (prompt.answer.value and 
                         prompt.answer.confidence >= 0.7 and 
                         len(prompt.answer.evidence) > 0)
                    )
                    
                    if is_fulfilled:
                        fulfilled_options.append({
                            "prompt_id": option.prompt_id,
                            "description": option.description,
                            "weight": option.weight,
                            "confidence": prompt.answer.confidence,
                            "value": prompt.answer.value or "ja"
                        })
                
                # Prüfe Gruppenlogik
                group_fulfilled = False
                
                if group.logic == "OR":
                    # Mindestens min_required Optionen müssen erfüllt sein
                    group_fulfilled = len(fulfilled_options) >= group.min_required
                elif group.logic == "AND":
                    # ALLE Optionen müssen erfüllt sein
                    group_fulfilled = len(fulfilled_options) == total_options
                
                group_evaluations.append({
                    "group_id": group.group_id,
                    "group_name": group.group_name,
                    "logic": group.logic,
                    "total_options": total_options,
                    "fulfilled_options": len(fulfilled_options),
                    "fulfilled_details": fulfilled_options,
                    "is_fulfilled": group_fulfilled,
                    "is_mandatory": group.is_mandatory
                })
                
                # Zähle für Gesamtbewertung
                if group.is_mandatory:
                    total_count += 1
                    if group_fulfilled:
                        fulfilled_count += 1
                    else:
                        error_msg = group.error_msg or f"Gruppe '{group.group_name}' nicht erfüllt"
                        errors.append(error_msg)
            
            is_qualified = len(errors) == 0
        
        # 2. FALLBACK: Legacy must_criteria
        elif mandanten_config.must_criteria:
            evaluation_method = "must_criteria_legacy"
            errors = self.validate_must_criteria(filled_protocol, mandanten_config)
            total_count = len(mandanten_config.must_criteria)
            fulfilled_count = total_count - len(errors)
            is_qualified = len(errors) == 0
            
            # Build criteria details for legacy
            for criterion in mandanten_config.must_criteria:
                prompt = prompts_by_id.get(criterion.prompt_id)
                if prompt:
                    is_fulfilled = prompt.answer.checked == criterion.expected
                    group_evaluations.append({
                        "group_id": f"legacy_{criterion.prompt_id}",
                        "group_name": f"Legacy Criterion {criterion.prompt_id}",
                        "logic": "AND",
                        "total_options": 1,
                        "fulfilled_options": 1 if is_fulfilled else 0,
                        "fulfilled_details": [{
                            "prompt_id": criterion.prompt_id,
                            "description": prompt.question[:100],
                            "weight": 1.0,
                            "confidence": prompt.answer.confidence,
                            "value": "ja" if prompt.answer.checked else "nein"
                        }] if is_fulfilled else [],
                        "is_fulfilled": is_fulfilled,
                        "is_mandatory": True
                    })
        
        # 3. FALLBACK: Implizite Qualifikationserkennung
        else:
            evaluation_method = "implicit_detection"
            
            qualification_keywords = [
                'ausbildung', 'studium', 'abschluss', 
                'berufserfahrung', 'jahre erfahrung',
                'zertifikat', 'qualifikation', 
                'deutschkenntnisse', 'führerschein'
            ]
            
            implicit_qualifications = []
            
            for page in filled_protocol.pages:
                for prompt in page.prompts:
                    question_lower = prompt.question.lower()
                    
                    is_qualification_question = any(
                        keyword in question_lower 
                        for keyword in qualification_keywords
                    )
                    
                    if is_qualification_question:
                        is_fulfilled = (
                            prompt.answer.checked == True or
                            (prompt.answer.value and 
                             prompt.answer.confidence >= 0.7 and 
                             len(prompt.answer.evidence) > 0)
                        )
                        
                        if is_fulfilled:
                            implicit_qualifications.append({
                                "prompt_id": prompt.id,
                                "question": prompt.question,
                                "confidence": prompt.answer.confidence,
                                "value": prompt.answer.value or "ja"
                            })
                            
                            group_evaluations.append({
                                "group_id": f"implicit_{prompt.id}",
                                "group_name": "Implizit erkannte Qualifikation",
                                "logic": "OR",
                                "total_options": 1,
                                "fulfilled_options": 1,
                                "fulfilled_details": [{
                                    "prompt_id": prompt.id,
                                    "description": prompt.question[:100],
                                    "weight": 1.0,
                                    "confidence": prompt.answer.confidence,
                                    "value": prompt.answer.value or "ja"
                                }],
                                "is_fulfilled": True,
                                "is_mandatory": False
                            })
            
            # Mindestens eine Qualifikation muss erfüllt sein
            is_qualified = len(implicit_qualifications) > 0
            fulfilled_count = len(implicit_qualifications)
            total_count = fulfilled_count  # Nur die gefundenen zählen
            
            if not is_qualified:
                errors.append("Keine Qualifikationsvoraussetzungen im Transkript erfüllt")
        
        # Build summary text
        if is_qualified:
            if total_count > 0:
                summary = f"Bewerber qualifiziert: {fulfilled_count}/{total_count} Kriterien erfüllt."
            else:
                summary = "Bewerber qualifiziert: Keine Qualifikationskriterien definiert."
        else:
            missing = total_count - fulfilled_count
            summary = f"Bewerber nicht qualifiziert: {missing}/{total_count} Kriterien nicht erfüllt."
        
        return {
            "is_qualified": is_qualified,
            "summary": summary,
            "fulfilled_count": fulfilled_count,
            "total_count": total_count,
            "errors": errors,
            "evaluation_method": evaluation_method,
            "group_evaluations": group_evaluations
        }
    
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


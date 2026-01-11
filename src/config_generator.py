"""Automatic config generator for creating mandanten YAML files from protocol templates."""
import re
from typing import Dict, Any, List
from pathlib import Path
import yaml

from models import PromptType


class ConfigGenerator:
    """Generates mandanten configuration YAML from protocol template."""
    
    def generate_config(
        self,
        protocol: Dict[str, Any],
        output_path: str = None
    ) -> Dict[str, Any]:
        """
        Generate configuration from protocol template.
        
        Args:
            protocol: Protocol template (JSON dict)
            output_path: Optional path to write YAML file
            
        Returns:
            Config dict that can be written to YAML
        """
        template_id = protocol.get("id")
        template_name = protocol.get("name", "Unknown")
        
        # Initialize config structure
        config = {
            "mandant_id": f"template_{template_id}",
            "protokoll_template_id": template_id,
            "heuristic_rules": self._generate_heuristic_rules(protocol),
            "info_page_names": self._extract_info_page_names(protocol),
            "grounding": self._extract_grounding_defaults(protocol),
            "aida_phase_mapping": self._generate_aida_mapping(protocol),
            "must_criteria": self._extract_must_criteria(protocol),
            "qualification_groups": self._extract_qualification_groups(protocol),  # Neu
            "routing_rules": [],  # Empty by default, user can add manually
            "implicit_defaults": self._generate_implicit_defaults(protocol)
        }
        
        # Write to file if path provided
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, "w", encoding="utf-8") as f:
                # Add header comment
                f.write(f"# Auto-generated config for: {template_name}\n")
                f.write(f"# Template ID: {template_id}\n")
                f.write(f"# Generated from protocol template\n\n")
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
            print(f"[OK] Config geschrieben: {output_file}")
        
        return config
    
    def _generate_heuristic_rules(self, protocol: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate heuristic rules from prompt questions."""
        rules = []
        
        # Collect patterns from prompts
        for page in protocol.get("pages", []):
            for prompt in page.get("prompts", []):
                question = prompt.get("question", "").lower()
                prompt_type = prompt.get("type")
                
                # Skip if no type or is info type
                if not prompt_type or prompt_type == "info":
                    continue
                
                # Extract key patterns
                if "fortbildung" in question or "qualifizierung" in question:
                    rules.append({
                        "pattern": "nachweis.*(fortbildungen|qualifizierungen)",
                        "type": "text_list",
                        "confidence": 0.90
                    })
                
                if "vollzeit" in question and any(x in question for x in ["stunden", "wochenstunden"]):
                    hours_match = re.search(r'(\d+)\s*(wochenstunden|stunden)', question)
                    if hours_match:
                        rules.append({
                            "pattern": f"(vollzeit|wochenstunden|{hours_match.group(1)})",
                            "type": "yes_no",
                            "confidence": 0.90
                        })
                
                if "vergütung" in question or "gehalt" in question:
                    rules.append({
                        "pattern": "vergütung.*(tv-l|tarif|€|euro)",
                        "type": "yes_no_with_details",
                        "confidence": 0.88
                    })
                
                if "weiterleiten" in question or "routing" in question:
                    rules.append({
                        "pattern": "alternativ.*weiterleiten",
                        "type": "routing_rule",
                        "confidence": 0.93
                    })
        
        # Remove duplicates
        seen = set()
        unique_rules = []
        for rule in rules:
            key = (rule["pattern"], rule["type"])
            if key not in seen:
                seen.add(key)
                unique_rules.append(rule)
        
        return unique_rules
    
    def _extract_info_page_names(self, protocol: Dict[str, Any]) -> List[str]:
        """Extract page names that contain info prompts."""
        info_pages = set()
        
        for page in protocol.get("pages", []):
            page_name = page.get("name", "")
            # Check if page contains info prompts
            has_info = any(
                prompt.get("type") == "info" 
                for prompt in page.get("prompts", [])
            )
            
            if has_info:
                info_pages.add(page_name)
        
        return list(info_pages)
    
    def _extract_grounding_defaults(self, protocol: Dict[str, Any]) -> Dict[str, Any]:
        """Extract default values from protocol (vollzeit_stunden, urlaub_tage, etc.)."""
        grounding = {}
        
        for page in protocol.get("pages", []):
            for prompt in page.get("prompts", []):
                question = prompt.get("question", "")
                q_lower = question.lower()
                
                # Extract Vollzeit hours
                if "vollzeit" in q_lower:
                    hours_match = re.search(r'(\d+)\s*(wochenstunden|stunden)', question)
                    if hours_match:
                        grounding["vollzeit_stunden"] = int(hours_match.group(1))
                
                # Extract Urlaubstage
                if "urlaub" in q_lower or "jahresurlaub" in q_lower:
                    days_match = re.search(r'(\d+)\s*tage', question, re.IGNORECASE)
                    if days_match:
                        grounding["urlaub_tage"] = int(days_match.group(1))
                
                # Extract Tarifvertrag
                if "tv-l" in q_lower or "tarif" in q_lower:
                    tarif_match = re.search(r'(tv-l[^(,]+)', question, re.IGNORECASE)
                    if tarif_match:
                        grounding["tarifvertrag"] = tarif_match.group(1).strip()
        
        return grounding
    
    def _generate_aida_mapping(self, protocol: Dict[str, Any]) -> Dict[str, List[int]]:
        """Generate AIDA phase mapping from prompts."""
        # Heuristic: 
        # - "Interest" phase: Kriterien-Seite (Zwingend, Wünschenswert)
        # - "Action" phase: Rahmenbedingungen-Seite (Vergütung, Vollzeit, Urlaub)
        
        aida_mapping = {
            "interest": [],
            "action": []
        }
        
        for page in protocol.get("pages", []):
            page_name = page.get("name", "").lower()
            
            for prompt in page.get("prompts", []):
                prompt_id = prompt.get("id")
                prompt_type = prompt.get("type")
                question = prompt.get("question", "").lower()
                
                # Skip info prompts
                if prompt_type == "info":
                    continue
                
                # Interest phase: Kriterien
                if any(x in page_name for x in ["kriterien", "bewerber erfüllt"]):
                    aida_mapping["interest"].append(prompt_id)
                
                # Action phase: Rahmenbedingungen
                elif any(x in page_name for x in ["rahmenbedingungen", "akzeptiert"]):
                    aida_mapping["action"].append(prompt_id)
                
                # Fallback: Check question content
                elif any(x in question for x in ["zwingend", "wünschenswert", "fortbildung", "abschluss", "erfahrung"]):
                    if prompt_id not in aida_mapping["interest"]:
                        aida_mapping["interest"].append(prompt_id)
                
                elif any(x in question for x in ["vollzeit", "urlaub", "vergütung", "gehalt"]):
                    if prompt_id not in aida_mapping["action"]:
                        aida_mapping["action"].append(prompt_id)
        
        return aida_mapping
    
    def _extract_must_criteria(self, protocol: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract must-have criteria from protocol."""
        must_criteria = []
        
        for page in protocol.get("pages", []):
            for prompt in page.get("prompts", []):
                question = prompt.get("question", "")
                prompt_id = prompt.get("id")
                
                # Look for "Zwingend:" prefix
                if question.lower().startswith("zwingend:"):
                    must_criteria.append({
                        "prompt_id": prompt_id,
                        "expected": True,
                        "error_msg": f"Zwingendes Kriterium nicht erfüllt: {question[:60]}..."
                    })
        
        return must_criteria
    
    def _extract_qualification_groups(self, protocol: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract qualification groups with intelligent pattern detection.
        
        Erkennt:
        1. Einzelne Qualifikationsfragen (automatisch als OR-Gruppe)
        2. Mehrfachoptionen in einer Frage (z.B. "Ausbildung als A, B oder C?")
        3. Mehrere verwandte Fragen (z.B. gruppiert nach "Ausbildung", "Erfahrung")
        """
        qualification_groups = []
        
        # Kategorien für Gruppierung
        categories = {
            "ausbildung": {
                "keywords": ["ausbildung", "studium", "abschluss", "qualifikation"],
                "patterns": [
                    r"ausbildung\s+(?:als|zum|zur)\s+([\w\s,\-]+(?:\s+oder\s+[\w\s,\-]+)*)",
                    r"abschluss\s+(?:als|in)\s+([\w\s,\-]+(?:\s+oder\s+[\w\s,\-]+)*)",
                    r"studium\s+(?:der|in)?\s*([\w\s,\-]+(?:\s+oder\s+[\w\s,\-]+)*)"
                ]
            },
            "erfahrung": {
                "keywords": ["berufserfahrung", "jahre erfahrung", "erfahrung in", "erfahrung als"],
                "patterns": [
                    r"(\d+)\s+jahre?\s+(?:berufs)?erfahrung",
                    r"erfahrung\s+(?:als|in)\s+([\w\s,\-]+)"
                ]
            },
            "zertifikate": {
                "keywords": ["zertifikat", "zertifizierung", "lizenz", "berechtigung", "nachweis"],
                "patterns": [
                    r"zertifikat\s+([\w\s,\-]+(?:\s+oder\s+[\w\s,\-]+)*)",
                    r"nachweis\s+(?:über|von)?\s*([\w\s,\-]+)"
                ]
            },
            "sprachen": {
                "keywords": ["sprachkenntnisse", "deutschkenntnisse", "englischkenntnisse"],
                "patterns": [
                    r"(deutsch|englisch|französisch)kenntnisse.*([abc][12])",
                    r"sprach(?:kenntnisse|niveau).*([abc][12])"
                ]
            },
            "fuehrerschein": {
                "keywords": ["führerschein", "fahrerlaubnis"],
                "patterns": [
                    r"führerschein.*klasse\s+([a-z0-9,\s]+)"
                ]
            }
        }
        
        # Sammle Fragen nach Kategorie
        categorized_questions = {cat: [] for cat in categories}
        
        for page in protocol.get("pages", []):
            for prompt in page.get("prompts", []):
                question = prompt.get("question", "")
                question_lower = question.lower()
                prompt_id = prompt.get("id")
                
                # Skip Info-Prompts und Routing-Fragen
                prompt_type = prompt.get("type", "").lower()
                if prompt_type in ["info", "recruiter_instruction"]:
                    continue
                
                # Skip explizit als "Zwingend:" markierte (werden bereits in must_criteria erfasst)
                if question_lower.startswith("zwingend:"):
                    continue
                
                # Kategorisiere Frage
                for category, config in categories.items():
                    if any(keyword in question_lower for keyword in config["keywords"]):
                        categorized_questions[category].append({
                            "prompt_id": prompt_id,
                            "question": question,
                            "page": page.get("name", ""),
                            "question_lower": question_lower
                        })
                        break
        
        # Erstelle Gruppen aus kategorisierten Fragen
        group_counter = 1
        
        for category, questions in categorized_questions.items():
            if not questions:
                continue
            
            # Prüfe ob einzelne Frage mehrere Optionen enthält
            if len(questions) == 1:
                question_text = questions[0]["question"]
                question_lower = questions[0]["question_lower"]
                
                # Suche nach "oder" Pattern für Mehrfachoptionen
                if " oder " in question_lower:
                    options = []
                    
                    # Versuche Optionen zu extrahieren
                    options_extracted = False
                    for pattern in categories[category].get("patterns", []):
                        match = re.search(pattern, question_lower, re.IGNORECASE)
                        if match and match.groups():
                            # Extrahiere Optionen (getrennt durch "oder" oder ",")
                            options_text = match.group(1)
                            option_list = re.split(r'\s+oder\s+|,\s*(?:oder\s+)?', options_text)
                            
                            for opt_text in option_list:
                                opt_text = opt_text.strip()
                                if opt_text and len(opt_text) > 2:
                                    options.append({
                                        "prompt_id": questions[0]["prompt_id"],
                                        "description": opt_text.title(),
                                        "weight": 1.0
                                    })
                            
                            if options:
                                options_extracted = True
                                break
                    
                    if not options_extracted or not options:
                        # Fallback: Eine Option für die gesamte Frage
                        options = [{
                            "prompt_id": questions[0]["prompt_id"],
                            "description": question_text[:100],
                            "weight": 1.0
                        }]
                    
                    qualification_groups.append({
                        "group_id": f"qual_group_{group_counter}",
                        "group_name": f"Qualifikation: {category.replace('_', ' ').title()}",
                        "logic": "OR",
                        "options": options,
                        "min_required": 1,
                        "is_mandatory": True,
                        "error_msg": f"Keine der erforderlichen {category.replace('_', ' ')}-Qualifikationen erfüllt"
                    })
                    group_counter += 1
                else:
                    # Einzelne Frage ohne Optionen → einfache Gruppe
                    qualification_groups.append({
                        "group_id": f"qual_group_{group_counter}",
                        "group_name": f"Qualifikation: {category.replace('_', ' ').title()}",
                        "logic": "OR",
                        "options": [{
                            "prompt_id": questions[0]["prompt_id"],
                            "description": question_text[:100],
                            "weight": 1.0
                        }],
                        "min_required": 1,
                        "is_mandatory": True,
                        "error_msg": f"{category.replace('_', ' ').title()}-Qualifikation nicht erfüllt"
                    })
                    group_counter += 1
            
            else:
                # Mehrere Fragen in der Kategorie → OR-Gruppe (mindestens eine muss erfüllt sein)
                options = []
                for q in questions:
                    options.append({
                        "prompt_id": q["prompt_id"],
                        "description": q["question"][:100],
                        "weight": 1.0
                    })
                
                qualification_groups.append({
                    "group_id": f"qual_group_{group_counter}",
                    "group_name": f"Qualifikation: {category.replace('_', ' ').title()}",
                    "logic": "OR",
                    "options": options,
                    "min_required": 1,
                    "is_mandatory": True,
                    "error_msg": f"Keine der erforderlichen {category.replace('_', ' ')}-Qualifikationen erfüllt"
                })
                group_counter += 1
        
        return qualification_groups
    
    def _generate_implicit_defaults(self, protocol: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate implicit defaults (e.g., B2 German for German conversation)."""
        implicit_defaults = []
        
        for page in protocol.get("pages", []):
            for prompt in page.get("prompts", []):
                question = prompt.get("question", "").lower()
                prompt_id = prompt.get("id")
                
                # B2 Deutschkenntnisse
                if "deutschkenntnisse" in question and "b2" in question:
                    implicit_defaults.append({
                        "prompt_id": prompt_id,
                        "reasoning": "Gespräch wurde auf Deutsch geführt",
                        "default_answer": {
                            "checked": True,
                            "value": "ja",
                            "confidence": 0.8,
                            "notes": "Implizit angenommen (Gespräch auf Deutsch)"
                        }
                    })
        
        return implicit_defaults


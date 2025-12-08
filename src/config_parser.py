"""Config parser for extracting grounding information from protocol."""
import re
from typing import Dict, Any, List


class ConfigParser:
    """Extracts grounding information from info pages (e.g. Weitere Informationen)."""
    
    def extract_grounding(self, page_prompts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract grounding info from 'Weitere Informationen' page prompts."""
        grounding = {}
        
        for prompt in page_prompts:
            question = prompt.get("question", "")
            
            # Extract Region
            if match := re.search(r'Region\s*["\']?([^"\'!]+)["\']?', question, re.IGNORECASE):
                grounding["region"] = match.group(1).strip()
            
            # Extract Standort/Adresse
            if match := re.search(r'(Kita \w+),\s*([^,]+,\s*\d{5}[^,]*)', question):
                grounding["standort"] = {
                    "name": match.group(1),
                    "adresse": match.group(2).strip()
                }
            
            # Extract Ansprechpartner
            if match := re.search(r'Ansprechpartner.*?:\s*(.+)', question, re.IGNORECASE):
                grounding["ansprechpartner"] = match.group(1).strip()
            
            # Extract Gehaltskorridor
            if match := re.search(r'([\d\.\s]+)\s*€.*?bis.*?([\d\.\s]+)\s*€', question):
                min_gehalt_str = re.sub(r'[\.\s]', '', match.group(1))
                max_gehalt_str = re.sub(r'[\.\s]', '', match.group(2))
                try:
                    grounding["gehalt_range"] = {
                        "min": int(min_gehalt_str),
                        "max": int(max_gehalt_str)
                    }
                except ValueError:
                    pass
            
            # Extract Vollzeit-Stunden
            if match := re.search(r'(\d+)\s*Wochenstunden', question, re.IGNORECASE):
                grounding["vollzeit_stunden"] = int(match.group(1))
            
            # Extract Urlaubstage
            if match := re.search(r'(\d+)\s*Tage.*?Urlaub', question, re.IGNORECASE):
                grounding["urlaub_tage"] = int(match.group(1))
        
        return grounding


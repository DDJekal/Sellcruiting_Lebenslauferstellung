"""Transformer to convert API questionnaire format to internal protocol format."""
from typing import Dict, Any, List
from collections import defaultdict


class QuestionnaireTransformer:
    """Transform API questionnaire to internal protocol format."""
    
    def transform(self, api_questionnaire: Dict[str, Any], campaign_id: str = None) -> Dict[str, Any]:
        """
        Transform API questionnaire format to internal protocol format.
        
        API Format:
        {
          "questions": [
            {
              "id": 67,
              "question": "...",
              "question_type": "string",
              "group": "Standort",
              "category": "standort",
              "category_order": 3
            }
          ]
        }
        
        Internal Format:
        {
          "id": 63,
          "name": "Protocol Name",
          "pages": [
            {
              "id": 90,
              "name": "Page Name",
              "position": 1,
              "prompts": [
                {
                  "id": 321,
                  "question": "...",
                  "type": "yes_no",
                  "position": 1
                }
              ]
            }
          ]
        }
        """
        # Check if API response already has pages format (transcript format)
        if "pages" in api_questionnaire and api_questionnaire.get("pages"):
            # Already in internal format - return as is (transcript from /campaigns/{id}/transcript/)
            return api_questionnaire
        
        # Otherwise transform from questions format (questionnaire from /questionnaire/{id})
        questions = api_questionnaire.get("questions", [])
        
        if not questions:
            raise ValueError("No questions found in API response")
        
        # Group questions by category (becomes pages)
        pages_by_category = defaultdict(list)
        category_orders = {}
        
        for question in questions:
            category = question.get("category") or question.get("group") or "Allgemein"
            category_order = question.get("category_order", 999)
            
            pages_by_category[category].append(question)
            
            if category not in category_orders:
                category_orders[category] = category_order
        
        # Build pages
        pages = []
        for position, (category, questions_in_category) in enumerate(
            sorted(pages_by_category.items(), key=lambda x: category_orders.get(x[0], 999)),
            start=1
        ):
            # Sort questions by priority within category
            sorted_questions = sorted(
                questions_in_category,
                key=lambda q: q.get("priority", 999)
            )
            
            # Build prompts
            prompts = []
            for prompt_position, question in enumerate(sorted_questions, start=1):
                prompt = {
                    "id": question.get("id"),
                    "question": question.get("question", ""),
                    "information": question.get("help_text") or question.get("context"),
                    "position": prompt_position,
                    "checked": None,
                    "is_template": False,
                    "type": self._map_question_type(question.get("question_type"))
                }
                prompts.append(prompt)
            
            # Create page
            page = {
                "id": position * 10,  # Generate page IDs
                "name": self._format_page_name(category),
                "position": position,
                "prompts": prompts
            }
            pages.append(page)
        
        # Build protocol
        protocol = {
            "id": int(campaign_id) if campaign_id else 0,
            "name": self._generate_protocol_name(pages),
            "pages": pages
        }
        
        return protocol
    
    def _map_question_type(self, api_type: str) -> str:
        """
        Map API question types to internal types.
        
        API types: string, text, number, boolean, select, multiselect, date
        Internal types: yes_no, yes_no_with_details, text, number, date, info
        """
        if not api_type:
            return "text"
        
        type_mapping = {
            "boolean": "yes_no",
            "string": "text",
            "text": "text",
            "number": "number",
            "date": "date",
            "select": "text",
            "multiselect": "text",
            "info": "info"
        }
        
        return type_mapping.get(api_type.lower(), "text")
    
    def _format_page_name(self, category: str) -> str:
        """Format category name to readable page name."""
        # Capitalize first letter of each word
        return category.replace("_", " ").title()
    
    def _generate_protocol_name(self, pages: List[Dict[str, Any]]) -> str:
        """Generate protocol name from pages."""
        if not pages:
            return "Gesprächsprotokoll"
        
        # Use first page name or default
        first_page = pages[0].get("name", "Gesprächsprotokoll")
        return f"Protokoll - {first_page}"


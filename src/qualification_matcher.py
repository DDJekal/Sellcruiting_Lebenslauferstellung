"""Smart Matcher: Maps extracted resume data to protocol questions."""
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from models import FilledProtocol, Resume, PromptAnswer, Evidence, PromptType


class QualificationMatcher:
    """
    Intelligenter Matcher der Resume-Daten (unstrukturiert) 
    mit Protokoll-Fragen (strukturiert) abgleicht.
    
    Workflow:
    1. Extractor versucht Fragen direkt zu beantworten
    2. QualificationMatcher reichert mit Resume-Daten an
    3. Lücken werden geschlossen, Qualifikationen werden gefunden
    """
    
    def __init__(self):
        """Initialize matcher with qualification patterns."""
        self.qualification_patterns = {
            "ausbildung": {
                "keywords": ["ausbildung", "lehre"],
                "education_types": ["ausbildung", "berufsausbildung", "lehre", "geselle", "fachkraft"],
            },
            "studium": {
                "keywords": ["studium", "bachelor", "master", "diplom", "hochschule", "universität"],
                "education_types": ["studium", "bachelor", "master", "diplom"],
            },
            "berufserfahrung": {
                "keywords": ["berufserfahrung", "erfahrung", "jahre", "arbeite"],
            },
            "zertifikat": {
                "keywords": ["zertifikat", "zertifizierung", "lizenz", "berechtigung", "nachweis"],
            },
            "sprachen": {
                "keywords": ["deutsch", "englisch", "französisch", "sprache"],
            },
            "fuehrerschein": {
                "keywords": ["führerschein", "fahrerlaubnis"],
            }
        }
    
    def enrich_protocol_with_resume(
        self,
        filled_protocol: FilledProtocol,
        resume: Resume,
        confidence_threshold: float = 0.85
    ) -> FilledProtocol:
        """
        Reichert Protokoll mit Resume-Daten an.
        
        Für jede Protokoll-Frage:
        1. Wenn bereits beantwortet (checked != null, confidence >= 0.7) → behalte Antwort
        2. Wenn nicht beantwortet → prüfe Resume-Daten
        3. Wenn Match gefunden → fülle automatisch aus
        
        Args:
            filled_protocol: Bereits vom Extractor gefülltes Protokoll
            resume: Extrahierter strukturierter Lebenslauf
            confidence_threshold: Minimale Confidence für Auto-Fill
            
        Returns:
            Angereichertes Protokoll
        """
        enriched_count = 0
        
        for page in filled_protocol.pages:
            for prompt in page.prompts:
                # Skip wenn bereits gut beantwortet
                if prompt.answer.checked is not None and prompt.answer.confidence >= 0.7:
                    continue
                
                # Skip Info-Prompts
                if prompt.inferred_type in [PromptType.INFO, PromptType.RECRUITER_INSTRUCTION]:
                    continue
                
                question_lower = prompt.question.lower()
                
                # Prüfe Kategorie der Frage
                matched_data = None
                
                # 1. AUSBILDUNG (Berufsausbildung)
                if self._is_ausbildung_question(question_lower):
                    matched_data = self._match_ausbildung(
                        question=prompt.question,
                        educations=resume.educations
                    )
                
                # 2. STUDIUM
                elif self._is_studium_question(question_lower):
                    matched_data = self._match_studium(
                        question=prompt.question,
                        educations=resume.educations
                    )
                
                # 3. BERUFSERFAHRUNG
                elif self._is_erfahrung_question(question_lower):
                    matched_data = self._match_erfahrung(
                        question=prompt.question,
                        experiences=resume.experiences
                    )
                
                # 4. ZERTIFIKATE
                elif self._is_zertifikat_question(question_lower):
                    matched_data = self._match_zertifikat(
                        question=prompt.question,
                        educations=resume.educations
                    )
                
                # Wenn Match gefunden → Protokoll aktualisieren
                if matched_data and matched_data["confidence"] >= confidence_threshold:
                    prompt.answer.checked = matched_data["checked"]
                    prompt.answer.value = matched_data["value"]
                    prompt.answer.confidence = matched_data["confidence"]
                    prompt.answer.notes = f"[AUTO-MATCH] {matched_data['notes']}"
                    
                    # Evidence basierend auf Resume-Daten
                    if matched_data.get("evidence_text"):
                        prompt.answer.evidence = [
                            Evidence(
                                span=matched_data["evidence_text"][:100],
                                turn_index=-1,  # Marker für "aus Resume extrahiert"
                                speaker="A"
                            )
                        ]
                    
                    enriched_count += 1
        
        return filled_protocol
    
    def _is_ausbildung_question(self, question: str) -> bool:
        """Prüft ob Frage nach Berufsausbildung fragt."""
        return any(kw in question for kw in ["ausbildung", "lehre"]) and \
               "studium" not in question
    
    def _is_studium_question(self, question: str) -> bool:
        """Prüft ob Frage nach Studium fragt."""
        return any(kw in question for kw in ["studium", "bachelor", "master", "diplom", "hochschule", "universität"])
    
    def _is_erfahrung_question(self, question: str) -> bool:
        """Prüft ob Frage nach Berufserfahrung fragt."""
        return any(kw in question for kw in ["berufserfahrung", "jahre erfahrung", "erfahrung in", "erfahrung als"])
    
    def _is_zertifikat_question(self, question: str) -> bool:
        """Prüft ob Frage nach Zertifikaten fragt."""
        return any(kw in question for kw in ["zertifikat", "lizenz", "berechtigung", "nachweis", "schulung"])
    
    def _match_ausbildung(
        self,
        question: str,
        educations: List[Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Matched Ausbildungsfrage mit Education-Einträgen.
        
        Beispiel:
        Frage: "Haben Sie eine Ausbildung als Pflegefachmann oder Krankenpfleger?"
        Educations: [{"description": "Ausbildung zum Pflegefachmann", ...}]
        → Match!
        """
        question_lower = question.lower()
        
        # Extrahiere gesuchte Ausbildungen aus Frage
        sought_qualifications = self._extract_options_from_question(question)
        
        for education in educations:
            description = education.description.lower()
            
            # Prüfe ob Ausbildung (nicht Studium/Schule)
            if not any(kw in description for kw in ["ausbildung", "lehre", "geselle", "fachkraft", "fachmann", "fachfrau"]):
                continue
            
            # Prüfe Overlap mit gesuchten Qualifikationen
            for sought in sought_qualifications:
                sought_lower = sought.lower()
                
                # Direkter Match
                if sought_lower in description or self._is_substring_match(sought_lower, description):
                    return {
                        "checked": True,
                        "value": f"ja ({education.description})",
                        "confidence": 0.95,
                        "notes": f"Aus Resume: {education.description}",
                        "evidence_text": f"Ausbildung: {education.description}"
                    }
                
                # Fuzzy Match (z.B. "Pflegefachmann" vs "Pflegefachkraft")
                if self._fuzzy_match(sought_lower, description):
                    return {
                        "checked": True,
                        "value": f"ja ({education.description})",
                        "confidence": 0.90,
                        "notes": f"Ähnliche Qualifikation aus Resume: {education.description}",
                        "evidence_text": f"Ausbildung: {education.description}"
                    }
            
            # Wenn keine spezifischen Qualifikationen gesucht, aber Ausbildung vorhanden
            if not sought_qualifications:
                return {
                    "checked": True,
                    "value": f"ja ({education.description})",
                    "confidence": 0.88,
                    "notes": f"Aus Resume: {education.description}",
                    "evidence_text": f"Ausbildung: {education.description}"
                }
        
        # Keine passende Ausbildung gefunden (aber nur wenn konkret gesucht wurde)
        if sought_qualifications:
            return {
                "checked": False,
                "value": "nein",
                "confidence": 0.75,
                "notes": "Keine passende Ausbildung im Resume gefunden",
                "evidence_text": None
            }
        
        return None
    
    def _match_studium(
        self,
        question: str,
        educations: List[Any]
    ) -> Optional[Dict[str, Any]]:
        """Matched Studiums-Frage mit Education-Einträgen."""
        question_lower = question.lower()
        
        # Extrahiere gesuchte Studiengänge
        sought_qualifications = self._extract_options_from_question(question)
        
        for education in educations:
            description = education.description.lower()
            
            # Prüfe ob Studium
            if not any(kw in description for kw in ["bachelor", "master", "diplom", "studium"]):
                continue
            
            # Prüfe Overlap
            for sought in sought_qualifications:
                sought_lower = sought.lower()
                
                if sought_lower in description or self._is_substring_match(sought_lower, description):
                    return {
                        "checked": True,
                        "value": f"ja ({education.description})",
                        "confidence": 0.95,
                        "notes": f"Aus Resume: {education.description}",
                        "evidence_text": f"Studium: {education.description}"
                    }
                
                if self._fuzzy_match(sought_lower, description):
                    return {
                        "checked": True,
                        "value": f"ja ({education.description})",
                        "confidence": 0.90,
                        "notes": f"Ähnlicher Studiengang aus Resume: {education.description}",
                        "evidence_text": f"Studium: {education.description}"
                    }
            
            # Generisches Studium
            if not sought_qualifications:
                return {
                    "checked": True,
                    "value": f"ja ({education.description})",
                    "confidence": 0.88,
                    "notes": f"Aus Resume: {education.description}",
                    "evidence_text": f"Studium: {education.description}"
                }
        
        return None
    
    def _match_erfahrung(
        self,
        question: str,
        experiences: List[Any]
    ) -> Optional[Dict[str, Any]]:
        """Matched Erfahrungsfrage mit Experience-Einträgen."""
        question_lower = question.lower()
        
        # Prüfe auf Mindest-Jahre
        min_years_match = re.search(r"(\d+)\s+jahre?", question_lower)
        required_years = int(min_years_match.group(1)) if min_years_match else None
        
        # Berechne Gesamterfahrung
        total_years = 0
        relevant_experiences = []
        
        for exp in experiences:
            # Skip Praktika und sehr kurze Jobs
            if exp.employment_type in ["Praktikum"]:
                continue
            
            if exp.start:
                try:
                    start_year = int(exp.start[:4])
                    end_year = int(exp.end[:4]) if exp.end else datetime.now().year
                    years = max(0, end_year - start_year)
                    
                    # Nur Hauptjobs zählen voll
                    if exp.employment_type in ["Hauptjob", "Vollzeit", None]:
                        total_years += years
                        relevant_experiences.append(exp)
                    elif exp.employment_type in ["Werkstudent", "Duales Studium"]:
                        # Werkstudent/Duales Studium mit 50% werten
                        total_years += years * 0.5
                        relevant_experiences.append(exp)
                except:
                    pass
        
        if required_years:
            has_enough = total_years >= required_years
            return {
                "checked": has_enough,
                "value": f"ja (ca. {total_years:.1f} Jahre)" if has_enough else f"nein (nur ca. {total_years:.1f} Jahre)",
                "confidence": 0.90,
                "notes": f"Berechnet aus Resume: ca. {total_years:.1f} Jahre Gesamterfahrung",
                "evidence_text": f"Ca. {total_years:.1f} Jahre Berufserfahrung aus {len(relevant_experiences)} Positionen"
            }
        
        # Allgemeine Erfahrungsfrage
        if relevant_experiences:
            return {
                "checked": True,
                "value": f"ja (ca. {total_years:.1f} Jahre)",
                "confidence": 0.88,
                "notes": f"Berufserfahrung aus Resume: {len(relevant_experiences)} Positionen",
                "evidence_text": f"{len(relevant_experiences)} Positionen, ca. {total_years:.1f} Jahre Erfahrung"
            }
        
        return None
    
    def _match_zertifikat(
        self,
        question: str,
        educations: List[Any]
    ) -> Optional[Dict[str, Any]]:
        """Matched Zertifikats-Frage mit Education-Einträgen."""
        question_lower = question.lower()
        
        # Suche nach Zertifikaten/Schulungen
        sought_qualifications = self._extract_options_from_question(question)
        
        for education in educations:
            description = education.description.lower()
            
            # Prüfe ob Zertifikat/Schulung
            if not any(kw in description for kw in ["zertifikat", "zertifizierung", "schulung", "nachweis", "lizenz"]):
                continue
            
            # Prüfe Overlap
            for sought in sought_qualifications:
                sought_lower = sought.lower()
                
                if sought_lower in description or self._is_substring_match(sought_lower, description):
                    return {
                        "checked": True,
                        "value": f"ja ({education.description})",
                        "confidence": 0.92,
                        "notes": f"Aus Resume: {education.description}",
                        "evidence_text": f"Zertifikat: {education.description}"
                    }
            
            # Generisches Zertifikat
            if not sought_qualifications:
                return {
                    "checked": True,
                    "value": f"ja ({education.description})",
                    "confidence": 0.85,
                    "notes": f"Aus Resume: {education.description}",
                    "evidence_text": f"Zertifikat: {education.description}"
                }
        
        return None
    
    def _extract_options_from_question(self, question: str) -> List[str]:
        """
        Extrahiert Optionen aus Frage.
        
        "Haben Sie eine Ausbildung als Pflegefachmann, Krankenpfleger oder Altenpfleger?"
        → ["Pflegefachmann", "Krankenpfleger", "Altenpfleger"]
        """
        # Pattern: Text nach "als", getrennt durch "," oder "oder"
        match = re.search(r"als\s+([\w\s,\-\/]+(?:\s+oder\s+[\w\s,\-\/]+)*)", question, re.IGNORECASE)
        if match:
            options_text = match.group(1)
            options = re.split(r'\s+oder\s+|,\s*', options_text)
            return [opt.strip() for opt in options if opt.strip() and len(opt.strip()) > 2]
        
        # Alternative: Nach "zum/zur" suchen
        match = re.search(r"zum|zur\s+([\w\s,\-\/]+(?:\s+oder\s+[\w\s,\-\/]+)*)", question, re.IGNORECASE)
        if match:
            options_text = match.group(1)
            options = re.split(r'\s+oder\s+|,\s*', options_text)
            return [opt.strip() for opt in options if opt.strip() and len(opt.strip()) > 2]
        
        return []
    
    def _is_substring_match(self, sought: str, actual: str) -> bool:
        """Prüft ob sought in actual enthalten ist (flexibel)."""
        # Entferne Füllwörter
        stop_words = ["zum", "zur", "als", "der", "die", "das", "eine", "ein"]
        
        sought_clean = sought
        for word in stop_words:
            sought_clean = sought_clean.replace(word, "").strip()
        
        return sought_clean in actual if len(sought_clean) > 3 else False
    
    def _fuzzy_match(self, sought: str, actual: str, threshold: float = 0.5) -> bool:
        """
        Einfacher Fuzzy-Match für ähnliche Begriffe.
        
        "Pflegefachmann" ≈ "Pflegefachkraft"
        "Pflegefachmann" ≈ "Gesundheits- und Krankenpfleger" (beide Pflege)
        "Elektriker" ≈ "Elektroniker"
        """
        # Extrahiere Kernwörter (ohne "Ausbildung", "zum", etc.)
        stop_words = ["ausbildung", "zum", "zur", "als", "der", "die", "das", "eine", "ein", "bachelor", "master", "und"]
        
        sought_words = set(w for w in sought.split() if w not in stop_words and len(w) > 3)
        actual_words = set(w for w in actual.split() if w not in stop_words and len(w) > 3)
        
        if not sought_words or not actual_words:
            return False
        
        # Prüfe Überlappung
        overlap = sought_words & actual_words
        similarity = len(overlap) / max(len(sought_words), len(actual_words))
        
        # Zusätzlich: Prüfe auf gemeinsame Wortstämme (z.B. "pflege" in beiden)
        # Für Pflege-Bereich: Alle mit "pflege" im Namen sind ähnlich
        sought_stems = set()
        actual_stems = set()
        
        for word in sought_words:
            if "pflege" in word.lower():
                sought_stems.add("pflege")
            if "elektr" in word.lower():
                sought_stems.add("elektr")
            if "inform" in word.lower():
                sought_stems.add("inform")
        
        for word in actual_words:
            if "pflege" in word.lower() or "kranken" in word.lower() or "alten" in word.lower():
                actual_stems.add("pflege")
            if "elektr" in word.lower():
                actual_stems.add("elektr")
            if "inform" in word.lower():
                actual_stems.add("inform")
        
        stem_overlap = sought_stems & actual_stems
        if stem_overlap:
            similarity = max(similarity, 0.7)  # Stem-Match gibt mindestens 0.7
        
        return similarity >= threshold

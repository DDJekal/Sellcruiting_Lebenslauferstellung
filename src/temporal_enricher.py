"""Temporal enrichment using hybrid approach: dateparser + optional MCP."""
import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class TemporalEnricher:
    """
    Enriches transcripts with temporal context using hybrid approach.
    
    Phase 1: dateparser (always) - fast, deterministic, free
    Phase 2: MCP validation (optional) - for ambiguous cases only
    """
    
    MONTH_MAP = {
        'januar': 1, 'februar': 2, 'märz': 3, 'april': 4,
        'mai': 5, 'juni': 6, 'juli': 7, 'august': 8,
        'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12
    }
    
    # Patterns for temporal expressions
    TEMPORAL_PATTERNS = [
        r'vor\s+\d+\s+(?:jahr(?:en)?|monat(?:en)?|woche(?:n)?|tag(?:en)?)',
        r'seit\s+\d+\s+(?:jahr(?:en)?|monat(?:en)?|woche(?:n)?|tag(?:en)?)',
        r'seit\s+(?:januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4}',
        r'ab\s+(?:januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)(?:\s+\d{4})?',
        r'(?:anfang|mitte|ende)\s+(?:januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)(?:\s+\d{4})?',
        r'letzt(?:es|en|em)\s+(?:jahr|monat|woche)',
        r'nächst(?:es|en|em)\s+(?:jahr|monat|woche)',
        r'dies(?:es|en|em)\s+(?:jahr|monat)',
        r'20[0-3]\d',  # Years 2000-2039
    ]
    
    # Ambiguous patterns that might need MCP validation
    AMBIGUOUS_PATTERNS = [
        r'\b(damals|zu\s+der\s+zeit|währenddessen)\b',
        r'\b(kurz\s+(?:darauf|danach|zuvor))\b',
        r'\b(einige\s+(?:zeit|jahre|monate))\b',
    ]
    
    def __init__(self, reference_timestamp: Optional[int] = None):
        """
        Initialize enricher with reference timestamp.
        
        Args:
            reference_timestamp: Unix timestamp (seconds) as reference point.
                                If None, uses current time.
        """
        if reference_timestamp:
            self.reference_date = datetime.fromtimestamp(reference_timestamp)
        else:
            self.reference_date = datetime.now()
        
        # MCP client (lazy loaded)
        self._mcp_client = None
    
    def enrich_transcript(
        self, 
        transcript: List[Dict[str, str]], 
        use_mcp: bool = False
    ) -> List[Dict[str, str]]:
        """
        Enrich transcript with temporal annotations.
        
        Args:
            transcript: List of turns with 'speaker' and 'text'
            use_mcp: If True, use MCP for validation of ambiguous cases
            
        Returns:
            Enriched transcript with temporal annotations
        """
        # Phase 1: dateparser enrichment (always)
        enriched = self._enrich_with_dateparser(transcript)
        
        # Phase 2: MCP validation (optional)
        if use_mcp:
            enriched = self._validate_with_mcp(enriched)
        
        return enriched
    
    def _enrich_with_dateparser(self, transcript: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Phase 1: Fast dateparser-based enrichment."""
        enriched = []
        
        for turn in transcript:
            enriched_text = self._annotate_temporal_expressions(turn['text'])
            enriched.append({
                'speaker': turn['speaker'],
                'text': enriched_text,
                'original_text': turn.get('text', '')  # Keep original
            })
        
        return enriched
    
    def _annotate_temporal_expressions(self, text: str) -> str:
        """Annotate temporal expressions in text."""
        enriched = text
        annotations = []
        
        for pattern in self.TEMPORAL_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                expression = match.group(0)
                annotation = self._parse_expression(expression)
                
                if annotation:
                    annotations.append({
                        'pos': match.end(),
                        'text': f" [{annotation}]"
                    })
        
        # Apply annotations in reverse order to maintain positions
        for ann in sorted(annotations, key=lambda x: x['pos'], reverse=True):
            # Check if not already annotated
            if '[' not in enriched[ann['pos']:ann['pos']+10]:
                enriched = enriched[:ann['pos']] + ann['text'] + enriched[ann['pos']:]
        
        return enriched
    
    def _parse_expression(self, expression: str) -> Optional[str]:
        """Parse temporal expression to annotation."""
        expr_lower = expression.lower()
        
        # "vor X Jahren/Monaten/Wochen/Tagen"
        match = re.match(r'vor\s+(\d+)\s+(jahr(?:en)?|monat(?:en)?|woche(?:n)?|tag(?:en)?)', expr_lower)
        if match:
            number = int(match.group(1))
            unit = match.group(2)
            
            if 'jahr' in unit:
                target = self.reference_date - relativedelta(years=number)
                return f"≈{target.year}"
            elif 'monat' in unit:
                target = self.reference_date - relativedelta(months=number)
                return f"≈{target.strftime('%m/%Y')}"
            elif 'woche' in unit:
                target = self.reference_date - timedelta(weeks=number)
                return f"≈{target.strftime('%d.%m.%Y')}"
            elif 'tag' in unit:
                target = self.reference_date - timedelta(days=number)
                return f"≈{target.strftime('%d.%m.%Y')}"
        
        # "seit X Jahren/Monaten"
        match = re.match(r'seit\s+(\d+)\s+(jahr(?:en)?|monat(?:en)?)', expr_lower)
        if match:
            number = int(match.group(1))
            unit = match.group(2)
            
            if 'jahr' in unit:
                target = self.reference_date - relativedelta(years=number)
                return f"Start ≈{target.year}"
            elif 'monat' in unit:
                target = self.reference_date - relativedelta(months=number)
                return f"Start ≈{target.strftime('%m/%Y')}"
        
        # "seit Monat Jahr"
        match = re.match(
            r'seit\s+(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+(\d{4})',
            expr_lower
        )
        if match:
            month_name = match.group(1)
            year = int(match.group(2))
            month = self.MONTH_MAP.get(month_name, 1)
            
            target = datetime(year, month, 1)
            delta = self.reference_date - target
            years = delta.days / 365.25
            
            if years >= 1:
                return f"Start {year}, vor ca. {years:.1f} J"
            else:
                months = delta.days // 30
                return f"Start {year}, vor ca. {months} M"
        
        # "letztes/letzten Jahr/Monat/Woche"
        match = re.match(r'letzt(?:es|en|em)\s+(jahr|monat|woche)', expr_lower)
        if match:
            unit = match.group(1)
            
            if unit == 'jahr':
                return f"{self.reference_date.year - 1}"
            elif unit == 'monat':
                last_month = self.reference_date - relativedelta(months=1)
                return f"{last_month.strftime('%m/%Y')}"
            elif unit == 'woche':
                last_week = self.reference_date - timedelta(weeks=1)
                return f"KW {last_week.isocalendar()[1]}"
        
        # "nächstes/nächsten Jahr/Monat"
        match = re.match(r'nächst(?:es|en|em)\s+(jahr|monat)', expr_lower)
        if match:
            unit = match.group(1)
            
            if unit == 'jahr':
                return f"{self.reference_date.year + 1}"
            elif unit == 'monat':
                next_month = self.reference_date + relativedelta(months=1)
                return f"{next_month.strftime('%m/%Y')}"
        
        # "dieses Jahr/Monat"
        match = re.match(r'dies(?:es|en|em)\s+(jahr|monat)', expr_lower)
        if match:
            unit = match.group(1)
            
            if unit == 'jahr':
                return f"{self.reference_date.year}"
            elif unit == 'monat':
                return f"{self.reference_date.strftime('%m/%Y')}"
        
        # Explicit year (2000-2039)
        match = re.match(r'(20[0-3]\d)', expression)
        if match:
            year = int(match.group(1))
            years_diff = self.reference_date.year - year
            
            if years_diff > 0:
                return f"vor {years_diff} J"
            elif years_diff < 0:
                return f"in {abs(years_diff)} J"
            else:
                return "aktuell"
        
        return None
    
    def _needs_mcp_validation(self, text: str) -> bool:
        """Check if text needs MCP validation."""
        # Check for ambiguous patterns
        for pattern in self.AMBIGUOUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        # Check for complex timelines (multiple temporal expressions)
        temporal_count = len(re.findall(r'\[.*?\]', text))
        if temporal_count >= 3:
            return True
        
        return False
    
    def _validate_with_mcp(self, enriched_transcript: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Phase 2: MCP validation for ambiguous cases."""
        try:
            from anthropic import Anthropic
            
            if self._mcp_client is None:
                self._mcp_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            
            validated = []
            mcp_calls = 0
            
            for turn in enriched_transcript:
                if self._needs_mcp_validation(turn['text']):
                    validated_turn = self._call_mcp_validation(turn)
                    mcp_calls += 1
                else:
                    validated_turn = turn
                
                validated.append(validated_turn)
            
            print(f"   [INFO] MCP-Validierung: {mcp_calls}/{len(enriched_transcript)} Turns")
            return validated
            
        except ImportError:
            print("   [WARN] anthropic nicht installiert, überspringe MCP-Validierung")
            return enriched_transcript
        except Exception as e:
            print(f"   [WARN] MCP-Validierung fehlgeschlagen: {e}")
            return enriched_transcript
    
    def _call_mcp_validation(self, turn: Dict[str, str]) -> Dict[str, str]:
        """Call MCP to validate/enhance temporal annotations."""
        try:
            response = self._mcp_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": f"""Validiere und verbessere die temporalen Annotationen in diesem deutschen Text.

Referenzdatum: {self.reference_date.strftime('%Y-%m-%d')}
Text: {turn['text']}

Aufgaben:
1. Prüfe bestehende [≈XXXX]-Annotationen auf Korrektheit
2. Ergänze fehlende kontextuelle Zeitreferenzen (z.B. "damals", "zu der Zeit")
3. Gib nur den verbesserten Text zurück, keine Erklärungen

Format: Behalte alle [≈...] Annotationen bei, ergänze bei Bedarf."""
                }]
            )
            
            validated_text = response.content[0].text.strip()
            
            return {
                'speaker': turn['speaker'],
                'text': validated_text,
                'original_text': turn.get('original_text', ''),
                'mcp_validated': True
            }
            
        except Exception as e:
            print(f"   [WARN] MCP-Call fehlgeschlagen: {e}")
            return turn
    
    def extract_temporal_context(self, transcript: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Extract temporal context summary from transcript.
        
        Returns dict with:
        - call_date: Date of the call
        - call_year, call_month: Components
        - mentioned_years: List of years mentioned
        """
        call_date = self.reference_date.strftime('%Y-%m-%d')
        mentioned_years = set()
        
        full_text = ' '.join(turn.get('text', '') for turn in transcript)
        
        # Extract years
        for match in re.finditer(r'\b(20[0-2]\d)\b', full_text):
            mentioned_years.add(int(match.group(1)))
        
        return {
            'call_date': call_date,
            'call_year': self.reference_date.year,
            'call_month': self.reference_date.month,
            'mentioned_years': sorted(mentioned_years)
        }


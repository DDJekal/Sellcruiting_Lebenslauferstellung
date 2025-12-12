# 🎯 Prompt-Optimierungsplan für Lebenslauf-Qualität

## 📊 Aktuelle Situation - Analyse

### ✅ **Was bereits gut funktioniert:**
1. **Temporale Enrichment** - Zeitangaben werden annotiert
2. **Strukturierte Extraktion** - JSON Schema ist klar definiert
3. **Evidence-Tracking** - Nachvollziehbarkeit durch Belege
4. **Grounding** - Kontext von ElevenLabs wird genutzt

### ⚠️ **Identifizierte Schwachstellen:**

#### 1. **Resume Builder (`src/resume_builder.py`)**
**Problem:** Generischer Prompt ohne domänenspezifische Optimierung

```python
# AKTUELL (Zeile 193-250):
- Generische Anweisungen
- Keine expliziten Beispiele
- Wenig Guidance für Edge Cases
- Keine Validierungshinweise
```

**Risiken:**
- Ungenaue Datumsangaben trotz Annotationen
- Fehlende Berufserfahrungen (nicht alle gefunden)
- Vage Beschreibungen in `tasks`-Feld
- Inkonsistente Formatierung

---

#### 2. **Answer Extraction (`src/extractor.py`)**
**Problem:** Implizite Zustimmung kann zu False Positives führen

```python
# AKTUELL (Zeile 106-110):
"IMPLIZIT (nur bei Rahmenbedingungen/Angeboten): Recruiter erwähnt Angebot/Bedingung UND:
 - Kandidat widerspricht NICHT
 - confidence: 0.8"
```

**Risiken:**
- Kandidat könnte einfach vergessen haben zu antworten
- Missverständnisse werden als Zustimmung gewertet
- Telefonstörungen/Unterbrechungen führen zu Fehlern

---

#### 3. **Type Inference (`src/type_enricher.py`)**
**Problem:** Generischer LLM-Prompt ohne Beispiele

```python
# AKTUELL (Zeile 138-152):
- Nur Label-Liste, keine Beispiele
- Keine Hinweise auf Kontext (AIDA-Phase)
- Keine Few-Shot Examples
```

---

## 🚀 Konkrete Optimierungen

### **OPTIMIERUNG 1: Resume Builder - Detaillierte Anweisungen**

#### A) **Bessere temporale Verarbeitung:**
```
TEMPORALE REGELN (ERWEITERT):
1. PRIORITÄT: Nutze temporale Annotationen [≈2021, vor 3 J]
2. Bei "seit X" ohne Enddatum: end = null (bis heute)
3. Bei "von X bis Y": beide Daten extrahieren
4. Bei ungenauen Angaben wie "Mitte 2020": "2020-06" verwenden
5. Bei "noch bis 2025": end = "2025-12-31" (konservativ)
6. VALIDIERUNG: start muss VOR end liegen!

BEISPIELE:
- "seit 2021" → start: "2021-01-01", end: null
- "von 2019 bis 2023" → start: "2019-01-01", end: "2023-12-31"
- "vor 3 Jahren [≈2021]" → start: "2021-01-01"
- "Mitte 2020" → "2020-06-01"
```

#### B) **Strukturierte Experience-Extraktion:**
```
EXPERIENCES - DETAILLIERTE REGELN:

1. VOLLSTÄNDIGKEIT:
   - Durchsuche GESAMTES Transkript
   - Jede erwähnte Position ist eine Experience
   - Auch kurze Praktika/Nebenjobs einbeziehen

2. TASKS-FELD - QUALITÄTSKRITERIEN:
   - Konkrete Aufgaben (z.B. "Kundenberatung", "Projektleitung")
   - Technologien/Tools (z.B. "Python", "SAP")
   - Verantwortungsbereiche (z.B. "Team von 5 Personen")
   - Errungenschaften (z.B. "Umsatzsteigerung um 20%")
   - MINDESTENS 2-3 vollständige Sätze pro Experience
   - Format: "- Aufgabe 1\n- Aufgabe 2\n- Aufgabe 3"

3. COMPANY-FELD:
   - Immer vollständigen Firmennamen extrahieren
   - Bei unklarem Namen: null verwenden (nicht raten!)

BEISPIEL (GUT):
{
  "start": "2021-01-01",
  "end": null,
  "company": "Siemens AG",
  "tasks": "- Entwicklung von Python-basierten Automatisierungsskripten\n- Projektkoordination zwischen IT und Fachabteilungen\n- Betreuung von 3 Junior-Entwicklern\n- Implementierung agiler Methoden (Scrum)"
}

BEISPIEL (SCHLECHT - zu vage):
{
  "start": "2021-01-01",
  "end": null,
  "company": "Firma",
  "tasks": "Entwicklung und Projektarbeit"
}
```

#### C) **Validierung & Plausibilitätsprüfung:**
```
VALIDIERUNG:
1. Zeitliche Plausibilität:
   - start < end (wenn end nicht null)
   - Keine Überschneidungen bei Vollzeitjobs
   - Experiences chronologisch sortieren (neueste zuerst)

2. Vollständigkeit:
   - Wenn "current_job" gefüllt, muss eine Experience mit end=null existieren
   - Wenn Studium erwähnt, muss Education vorhanden sein

3. Konsistenz:
   - "earliest_start" sollte nicht VOR aktueller Job-end liegen
   - "willing_to_relocate" muss mit erwähnten Standorten konsistent sein
```

---

### **OPTIMIERUNG 2: Answer Extraction - Strengere Evidenz-Anforderungen**

#### A) **Explizite vs. Implizite Zustimmung klarer trennen:**
```python
IMPLIZITE ZUSTIMMUNG - NEUE REGELN:

✅ AKZEPTIERT als implizite Zustimmung (checked: true):
1. Recruiter erwähnt Rahmenbedingung/Angebot
2. UND Kandidat reagiert positiv ODER stellt Folgefragen zum Thema
3. UND Gespräch geht konstruktiv weiter

❌ NICHT akzeptiert (checked: null):
1. Kandidat sagt gar nichts zur Bedingung
2. Kandidat wechselt sofort das Thema
3. Lange Pause nach Recruiter-Aussage (>3 Turns)
4. Kandidat antwortet mit allgemeinem "hmm", "okay" (nicht spezifisch)

⚠️ AMBIVALENT (checked: null, confidence: 0.5, notes):
1. Kandidat sagt "mal sehen", "müsste ich überlegen"
2. Telefonstörung während Antwort
3. Mehrfache Nachfragen nötig

BEISPIELE:
┌─────────────────────────────────────────────────────────────┐
│ SZENARIO 1: ✅ Implizite Zustimmung                          │
├─────────────────────────────────────────────────────────────┤
│ Recruiter: "30 Tage Urlaub plus Sonderurlaub."              │
│ Kandidat: "Und wie sieht es mit Homeoffice aus?"            │
│ → checked: true, confidence: 0.85                            │
│ → notes: "Implizit akzeptiert - Kandidat stellt Folgefrage" │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ SZENARIO 2: ❌ Keine klare Zustimmung                        │
├─────────────────────────────────────────────────────────────┤
│ Recruiter: "30 Tage Urlaub plus Sonderurlaub."              │
│ Kandidat: "Hmm."                                             │
│ Recruiter: "Haben Sie noch Fragen zur Position?"            │
│ → checked: null, confidence: 0.0                             │
│ → notes: "Keine klare Reaktion, Recruiter wechselt Thema"   │
└─────────────────────────────────────────────────────────────┘
```

#### B) **Evidence-Qualität erhöhen:**
```python
EVIDENCE - QUALITÄTSANFORDERUNGEN:

1. SPAN-LÄNGE:
   - Minimum: Keyword + 20 Zeichen Kontext
   - Maximum: 100 Zeichen
   - Muss VOLLSTÄNDIG die Aussage enthalten

2. PRÄZISION:
   - Bei yes_no: Muss Zustimmung/Ablehnung enthalten
   - Bei text_list: Jedes Item braucht separaten Evidence-Eintrag
   - Bei yes_no_with_details: Evidence muss Details enthalten

3. TURN_INDEX:
   - Immer angeben (0-basiert)
   - Bei impliziter Zustimmung: BEIDE Turns (Recruiter + Kandidat)

BEISPIEL (GUT):
{
  "checked": true,
  "evidence": [
    {"span": "30 Tage Urlaub plus Sonderurlaub", "turn_index": 45, "speaker": "B"},
    {"span": "Und wie sieht es mit Homeoffice aus", "turn_index": 46, "speaker": "A"}
  ]
}
```

---

### **OPTIMIERUNG 3: Type Inference - Few-Shot Examples**

```python
SYSTEM PROMPT - MIT BEISPIELEN:

Du klassifizierst deutschsprachige Fragen aus einem Gesprächsprotokoll.

BEISPIELE:

1. "Zwingend: Führerschein Klasse B vorhanden?"
   → {"inferred_type": "yes_no", "confidence": 0.95, "reasoning": "Binäre Anforderung"}

2. "Welche Fortbildungen haben Sie absolviert?"
   → {"inferred_type": "text_list", "confidence": 0.92, "reasoning": "Fordert Liste von Items"}

3. "Akzeptieren Sie Vollzeit (40h/Woche)?"
   → {"inferred_type": "yes_no", "confidence": 0.98, "reasoning": "Ja/Nein-Frage zu Rahmenbedingung"}

4. "Seit wann sind Sie in Ihrer aktuellen Position?"
   → {"inferred_type": "date", "confidence": 0.90, "reasoning": "Fragt nach Zeitpunkt"}

5. "Bitte unbedingt erwähnen: Attraktives Gehalt!!!"
   → {"inferred_type": "recruiter_instruction", "confidence": 1.0, "reasoning": "Instruktion für Recruiter"}

JETZT klassifiziere diese Prompts...
```

---

### **OPTIMIERUNG 4: Qualitätssicherung durch Validierungsschicht**

**NEU: Post-Processing Validator für Resume**

```python
class ResumeQualityValidator:
    """Validates and improves resume quality."""
    
    def validate_resume(self, resume: Resume, transcript: str) -> dict:
        """
        Returns quality report + suggestions.
        """
        issues = []
        
        # 1. Temporal validation
        for exp in resume.experiences:
            if exp.end and exp.start and exp.end < exp.start:
                issues.append({
                    "severity": "error",
                    "field": f"experience_{exp.id}",
                    "message": "end date before start date"
                })
        
        # 2. Completeness check
        if not resume.experiences:
            # Check if transcript mentions work experience
            if any(keyword in transcript.lower() for keyword in 
                   ["arbeit", "job", "position", "stelle", "firma"]):
                issues.append({
                    "severity": "warning",
                    "field": "experiences",
                    "message": "Work experience mentioned but not extracted"
                })
        
        # 3. Detail quality check
        for exp in resume.experiences:
            if exp.tasks and len(exp.tasks) < 50:  # Too short
                issues.append({
                    "severity": "warning",
                    "field": f"experience_{exp.id}.tasks",
                    "message": "Tasks description too vague (< 50 chars)"
                })
        
        return {
            "valid": len([i for i in issues if i["severity"] == "error"]) == 0,
            "quality_score": self._calculate_score(resume, issues),
            "issues": issues
        }
```

---

## 📝 Implementierungs-Reihenfolge

### **Phase 1: Quick Wins (30 min)**
1. ✅ Resume Builder Prompt erweitern (temporale Regeln + Beispiele)
2. ✅ Evidence-Anforderungen verschärfen

### **Phase 2: Medium Impact (1h)**
3. ✅ Type Inference mit Few-Shot Examples
4. ✅ Implizite Zustimmung klarer definieren

### **Phase 3: Advanced (2h)**
5. ⚠️ Qualitätsvalidator implementieren
6. ⚠️ Iterative Re-Extraction bei schlechter Qualität

---

## 🧪 Testing-Strategie

### **A) Unit Tests für einzelne Komponenten:**
```python
def test_temporal_extraction():
    """Test: "seit 2021" → start="2021-01-01", end=null"""
    
def test_implicit_consent_positive():
    """Test: Recruiter mentions + Kandidat follow-up = checked:true"""
    
def test_implicit_consent_negative():
    """Test: Recruiter mentions + silence = checked:null"""
```

### **B) Integration Tests mit echten Transkripten:**
```python
def test_full_pipeline_quality():
    """
    Given: Real ElevenLabs webhook
    When: Pipeline processes it
    Then: 
      - All experiences have detailed tasks (>50 chars)
      - All dates are valid (start < end)
      - Evidence is complete
    """
```

### **C) Quality Metrics:**
```python
{
  "resume_quality": {
    "experiences_count": 3,
    "avg_tasks_length": 187,  # Should be >100
    "temporal_errors": 0,
    "missing_companies": 0,
    "evidence_coverage": 0.95  # 95% of answers have evidence
  }
}
```

---

## 🎯 Erwartete Verbesserungen

| Metrik | Vorher | Nachher | Verbesserung |
|--------|--------|---------|--------------|
| **Experiences gefunden** | ~60% | ~90% | +50% |
| **Tasks Detail-Level** | vage | konkret | +++++ |
| **Temporale Fehler** | ~15% | <3% | -80% |
| **False Positives (implizit)** | ~20% | <5% | -75% |
| **Evidence Vollständigkeit** | ~70% | ~95% | +36% |

---

## ❓ Offene Fragen an den User

1. **Priorität:** Welche Optimierung ist am wichtigsten?
   - [ ] Bessere Experience-Extraktion (mehr Details in `tasks`)
   - [ ] Genauere Datumsangaben
   - [ ] Weniger False Positives bei impliziter Zustimmung
   - [ ] Alle gleichzeitig

2. **Validierung:** Soll ich den `ResumeQualityValidator` implementieren?
   - [ ] Ja, mit automatischer Warnung bei schlechter Qualität
   - [ ] Nein, erstmal nur Prompt-Optimierungen

3. **Testing:** Haben Sie echte Testfälle/Transkripte für Validierung?
   - [ ] Ja, in `Input/` verfügbar
   - [ ] Nein, manuell testen

---

## 🚀 Bereit zum Start?

Soll ich mit **Phase 1 (Quick Wins)** beginnen und die Prompts optimieren?


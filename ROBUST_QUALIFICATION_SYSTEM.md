# Robustes 3-Schichten-System für Qualifikationserkennung

## ✅ Problem gelöst

**Ursprüngliches Problem:**
- Transkripte sind unstrukturiert
- Kandidaten beantworten Fragen nicht direkt
- Qualifikationen werden beiläufig im Lebenslauf-Teil erwähnt
- System erkannte Qualifikationen nicht zuverlässig

**Lösung:**
Robustes 3-Schichten-System mit mehrfachem Fallback

## 🏗️ Architektur

### Schicht 1: Extractor (Direkte Antworten)
**Datei:** `src/extractor.py`

- Versucht Fragen direkt aus dem Transkript zu beantworten
- **NEU:** Erweitertes System-Prompt mit Regeln für Qualifikationsfragen
- Unterscheidet zwischen:
  - Qualifikationsfragen (faktische Antworten)
  - Rahmenbedingungen (Zustimmung)

**Beispiel:**
```
Frage: "Haben Sie eine Ausbildung als Pflegefachmann?"
Kandidat: "Ja, ich habe eine Ausbildung als Pflegefachmann."
→ Extractor findet: checked=True
```

### Schicht 2: ResumeBuilder (Unstrukturierte Extraktion)
**Datei:** `src/resume_builder.py` (bereits vorhanden)

- Extrahiert ALLE Qualifikationen aus dem gesamten Transkript
- Unabhängig von Protokoll-Fragen
- Erstellt strukturierten Lebenslauf mit:
  - `educations`: Alle Ausbildungen, Studiengänge
  - `experiences`: Alle Berufserfahrungen

**Beispiel:**
```
Kandidat (Turn 5): "Ich habe 2020 meine Ausbildung zum Pflegefachmann gemacht"
→ ResumeBuilder extrahiert: Education("Ausbildung zum Pflegefachmann", end="2020-05-01")
```

### Schicht 3: QualificationMatcher (Smart Matching)
**Datei:** `src/qualification_matcher.py` (NEU)

- Mappt Resume-Daten intelligent zu Protokoll-Fragen
- Nur wenn Extractor keine Antwort gefunden hat
- Features:
  - ✅ Direkte Matches ("Pflegefachmann" → "Pflegefachmann")
  - ✅ Fuzzy Matches ("Pflegefachmann" ≈ "Gesundheits- und Krankenpfleger")
  - ✅ Mehrfachoptionen ("A oder B oder C" → matched wenn eine Option erfüllt)
  - ✅ Berufserfahrung berechnen (aus Experience-Daten)
  - ✅ Äquivalente Qualifikationen (z.B. alle Pflege-Berufe)

## 📊 Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. EXTRACTOR                                                 │
│    Versucht direkte Antwort zu finden                        │
│    ↓                                                          │
│    ├─ Gefunden (checked != None, confidence >= 0.7)          │
│    │  → Behalte Antwort                                      │
│    │                                                          │
│    └─ Nicht gefunden (checked == None)                       │
│       → Weiter zu Schicht 2                                  │
└──────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. RESUME BUILDER                                            │
│    Extrahiert unstrukturierte Qualifikationen               │
│    → educations[], experiences[]                             │
└──────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. QUALIFICATION MATCHER                                     │
│    Matched Resume-Daten → Protokoll-Fragen                   │
│    ↓                                                          │
│    Für jede unbeantwortete Frage:                           │
│    1. Kategorie erkennen (Ausbildung/Erfahrung/...)         │
│    2. Resume-Daten durchsuchen                               │
│    3. Bei Match: Frage automatisch ausfüllen                │
│       confidence >= 0.85 → checked=True                      │
│       notes: "[AUTO-MATCH] Aus Resume: ..."                 │
└──────────────────────────────────────────────────────────────┘
```

## 🎯 Beispiel-Szenarien

### Szenario 1: Unstrukturierte Erwähnung

**Transkript:**
```
[Turn 5] A: "Also, ich habe 2020 meine Ausbildung zum Pflegefachmann 
             bei XY gemacht..."
[Turn 12] A: "Ich arbeite seit Mai 2020 bei den HEH-Kliniken als 
              Pflegefachmann."
```

**Protokoll-Frage:**
```
"Haben Sie eine Ausbildung als Pflegefachmann?"
```

**Ergebnis:**
- ✅ Extractor: Findet keine direkte Antwort (Turn 5 ist keine direkte Antwort auf Frage)
- ✅ ResumeBuilder: Extrahiert Education("Ausbildung zum Pflegefachmann")
- ✅ QualificationMatcher: Matched Education → Frage
  - `checked=True`
  - `value="ja (Ausbildung zum Pflegefachmann)"`
  - `confidence=0.95`
  - `notes="[AUTO-MATCH] Aus Resume: Ausbildung zum Pflegefachmann"`

### Szenario 2: Äquivalente Qualifikation

**Resume:**
```
Education: "Ausbildung zum Gesundheits- und Krankenpfleger"
```

**Protokoll-Frage:**
```
"Haben Sie eine Ausbildung als Pflegefachmann?"
```

**Ergebnis:**
- ✅ Fuzzy-Match erkennt: Beide sind Pflege-Berufe
- ✅ `checked=True`
- ✅ `confidence=0.90`
- ✅ `notes="Ähnliche Qualifikation aus Resume: Gesundheits- und Krankenpfleger"`

### Szenario 3: Mehrfachoptionen

**Protokoll-Frage:**
```
"Haben Sie eine Ausbildung als Pflegefachmann, Gesundheits- und 
 Krankenpfleger oder Altenpfleger?"
```

**Resume:**
```
Education: "Ausbildung zum Altenpfleger"
```

**Ergebnis:**
- ✅ Matcher extrahiert Optionen: ["Pflegefachmann", "Gesundheits- und Krankenpfleger", "Altenpfleger"]
- ✅ Findet Match mit "Altenpfleger"
- ✅ `checked=True` (eine Option erfüllt reicht!)

### Szenario 4: Berufserfahrung berechnen

**Protokoll-Frage:**
```
"Haben Sie mindestens 2 Jahre Berufserfahrung?"
```

**Resume:**
```
Experience:
  - Position: "Pflegefachmann", start: "2020-05-01", end: None
    employment_type: "Hauptjob"
```

**Ergebnis:**
- ✅ Berechnet: 2020 bis 2026 = ca. 6 Jahre
- ✅ `checked=True` (>= 2 Jahre)
- ✅ `value="ja (ca. 6.0 Jahre)"`
- ✅ `confidence=0.90`

## 🔧 Integration in Pipeline

**In `src/pipeline_processor.py`:**

```python
# 1. Extractor (versucht direkte Antworten)
extracted_answers = extractor.extract(transcript, shadow_types, grounding, all_prompts)
filled_protocol = mapper.map_answers(protocol, shadow_types, extracted_answers)

# 2. ResumeBuilder (unstrukturierte Extraktion)
applicant_resume = resume_builder.build_resume(
    transcript=transcript,
    elevenlabs_metadata=metadata,
    temporal_context=temporal_context
)

# 3. QualificationMatcher (Smart Matching) - NEU!
filled_protocol = qualification_matcher.enrich_protocol_with_resume(
    filled_protocol=filled_protocol,
    resume=applicant_resume.resume,
    confidence_threshold=0.85
)

# 4. Qualification Evaluation (mit enriched protocol!)
qualification_evaluation = validator.evaluate_qualification(
    filled_protocol, 
    mandanten_config
)
```

## ✅ Test-Ergebnisse

```
[OK] Test 1 (Unstrukturiert): BESTANDEN
     System erkennt Qualifikationen auch wenn beiläufig erwähnt
     
[OK] Test 2 (Äquivalent): BESTANDEN
     "Gesundheits- und Krankenpfleger" wird für "Pflegefachmann" akzeptiert
     
[OK] Test 3 (Mehrfachoptionen): BESTANDEN
     Bei "A oder B oder C" reicht eine erfüllte Option
```

## 🎉 Vorteile

1. **Maximale Robustheit**
   - 3 Chancen, Qualifikationen zu finden
   - Funktioniert auch bei unstrukturierten Transkripten

2. **Intelligentes Matching**
   - Äquivalente Qualifikationen werden erkannt
   - Fuzzy-Match für ähnliche Begriffe
   - Mehrfachoptionen werden korrekt gehandelt

3. **Transparenz**
   - Notes zeigen Quelle der Antwort
   - Confidence-Werte sind angemessen
   - Evidence wird mitgeführt

4. **Berufsgruppen-unabhängig**
   - Funktioniert für Pflege, IT, Handwerk, etc.
   - Generische Keywords statt hardcoded Berufe

## 📝 Verwendung

```python
from qualification_matcher import QualificationMatcher

matcher = QualificationMatcher()

enriched_protocol = matcher.enrich_protocol_with_resume(
    filled_protocol=filled_protocol,
    resume=resume,
    confidence_threshold=0.85  # Min. Confidence für Auto-Fill
)
```

## 🔍 Debugging

Evidence mit `turn_index=-1` bedeutet: Aus Resume extrahiert (nicht direkt aus Transkript).

Notes mit `[AUTO-MATCH]` Präfix zeigen: Wurde vom QualificationMatcher gefüllt.

---

**Das System ist jetzt möglichst robust und erkennt Qualifikationen zuverlässig, auch in unstrukturierten Transkripten!** ✅

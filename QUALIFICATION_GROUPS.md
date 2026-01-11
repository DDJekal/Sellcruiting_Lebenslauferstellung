# Qualification Groups - Dokumentation

## Übersicht

Das neue **Qualification Groups** System bietet eine flexible und robuste Möglichkeit, Qualifikationskriterien zu definieren und zu bewerten. Es unterstützt OR/AND-Logik und mehrere Optionen pro Gruppe.

## Features

### 1. Flexible Logik
- **OR-Logik**: Mindestens eine Option muss erfüllt sein
- **AND-Logik**: Alle Optionen müssen erfüllt sein
- **min_required**: Anzahl der minimal erforderlichen Optionen (bei OR)

### 2. Mehrfachoptionen
```yaml
# Beispiel: Kandidat braucht EINE der folgenden Ausbildungen
qualification_groups:
  - group_id: ausbildung_pflege
    group_name: "Ausbildung im Pflegebereich"
    logic: OR
    min_required: 1
    is_mandatory: true
    options:
      - prompt_id: 1001
        description: "Pflegefachmann/-frau"
      - prompt_id: 1002
        description: "Gesundheits- und Krankenpfleger/in"
      - prompt_id: 1003
        description: "Altenpfleger/in"
```

### 3. Automatische Erkennung
Das System erkennt automatisch Qualifikationsfragen anhand von Schlüsselwörtern:
- **Ausbildung**: "ausbildung", "studium", "abschluss", "qualifikation"
- **Erfahrung**: "berufserfahrung", "jahre erfahrung"
- **Zertifikate**: "zertifikat", "lizenz", "nachweis"
- **Sprachen**: "deutschkenntnisse", "sprachkenntnisse"
- **Führerschein**: "führerschein", "fahrerlaubnis"

### 4. Drei-Stufen-Fallback
1. **Qualification Groups** (Priorität 1) - Neue flexible Struktur
2. **Must Criteria** (Priorität 2) - Legacy-Support
3. **Implicit Detection** (Priorität 3) - Automatische Erkennung

## Verwendung

### Config erstellen (automatisch)

```python
from src.config_generator import ConfigGenerator

generator = ConfigGenerator()
config = generator.generate_config(
    protocol=protocol_json,
    output_path="config/mandanten/template_460.yaml"
)
```

Die Methode `_extract_qualification_groups()` erkennt automatisch:
- Fragen mit "oder" → mehrere Optionen in einer Gruppe
- Verwandte Fragen → gruppiert nach Kategorie
- Einzelne Qualifikationsfragen → einfache OR-Gruppe

### Config manuell anpassen

```yaml
qualification_groups:
  # Gruppe 1: Mindestens EINE Ausbildung (OR)
  - group_id: ausbildung
    group_name: "Ausbildung"
    logic: OR
    min_required: 1
    is_mandatory: true
    error_msg: "Keine Ausbildung nachgewiesen"
    options:
      - prompt_id: 101
        description: "Option A"
        weight: 1.0
      - prompt_id: 102
        description: "Option B"
        weight: 1.0

  # Gruppe 2: BEIDE Erfahrungen erforderlich (AND)
  - group_id: erfahrung
    group_name: "Erfahrung"
    logic: AND
    min_required: 2
    is_mandatory: true
    error_msg: "Nicht genug Erfahrung"
    options:
      - prompt_id: 201
        description: "2 Jahre Erfahrung"
        weight: 1.0
      - prompt_id: 202
        description: "Führungserfahrung"
        weight: 0.8
```

### Evaluation durchführen

```python
from src.validator import Validator

validator = Validator()
result = validator.evaluate_qualification(
    filled_protocol=filled_protocol,
    mandanten_config=mandanten_config
)

print(f"Qualifiziert: {result['is_qualified']}")
print(f"Summary: {result['summary']}")
print(f"Methode: {result['evaluation_method']}")

for group_eval in result['group_evaluations']:
    print(f"{group_eval['group_name']}: {group_eval['is_fulfilled']}")
```

## Beispiel-Szenarien

### Szenario 1: Pflegebereich mit mehreren Ausbildungen

**Anforderung**: Kandidat braucht EINE der folgenden Ausbildungen:
- Pflegefachmann/-frau
- Gesundheits- und Krankenpfleger/in
- Altenpfleger/in

**Config**:
```yaml
qualification_groups:
  - group_id: ausbildung_pflege
    logic: OR
    min_required: 1
    is_mandatory: true
    options:
      - prompt_id: 1001
        description: "Pflegefachmann/-frau"
      - prompt_id: 1002
        description: "Gesundheits- und Krankenpfleger/in"
      - prompt_id: 1003
        description: "Altenpfleger/in"
```

**Ergebnis**:
- Kandidat hat Ausbildung als Pflegefachmann → ✅ QUALIFIZIERT
- Kandidat hat keine der Ausbildungen → ❌ NICHT QUALIFIZIERT

### Szenario 2: Projektleiter mit mehreren Anforderungen

**Anforderung**: 
- Studium Elektrotechnik ODER verwandtes Fach (OR)
- UND mindestens 2 Jahre Erfahrung (AND)

**Config**:
```yaml
qualification_groups:
  - group_id: studium
    logic: OR
    min_required: 1
    is_mandatory: true
    options:
      - prompt_id: 301
        description: "Studium Elektrotechnik"
      - prompt_id: 302
        description: "Studium Maschinenbau"
  
  - group_id: erfahrung
    logic: AND
    min_required: 1
    is_mandatory: true
    options:
      - prompt_id: 401
        description: "2 Jahre Berufserfahrung"
```

**Ergebnis**:
- BEIDE Gruppen müssen erfüllt sein
- Kandidat braucht (Studium A ODER B) UND (2 Jahre Erfahrung)

## Vorteile

1. **Flexibilität**: OR/AND-Logik pro Gruppe
2. **Robustheit**: 3-Stufen-Fallback-System
3. **Automatik**: Intelligente Erkennung von Qualifikationsfragen
4. **Transparenz**: Detaillierte Evaluation mit Gruppenstatus
5. **Kompatibilität**: Legacy `must_criteria` werden weiterhin unterstützt

## Migration von must_criteria

**Alt** (Legacy):
```yaml
must_criteria:
  - prompt_id: 123
    expected: true
    error_msg: "Ausbildung fehlt"
```

**Neu** (Qualification Groups):
```yaml
qualification_groups:
  - group_id: ausbildung
    group_name: "Ausbildung"
    logic: OR
    min_required: 1
    is_mandatory: true
    error_msg: "Ausbildung fehlt"
    options:
      - prompt_id: 123
        description: "Ausbildung XYZ"
        weight: 1.0
```

**Vorteil**: Mit Qualification Groups können Sie später einfach weitere Optionen hinzufügen!

## Test

Führen Sie den Test aus:
```bash
python test_qualification_groups.py
```

Der Test demonstriert:
- Szenario 1: Kandidat MIT Qualifikation → qualifiziert
- Szenario 2: Kandidat OHNE Qualifikation → nicht qualifiziert
- Detaillierte Gruppen-Evaluation
- OR-Logik mit mehreren Optionen

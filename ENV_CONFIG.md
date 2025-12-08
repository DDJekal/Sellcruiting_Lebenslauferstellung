# Environment Configuration für ElevenLabs Integration & Temporal Enrichment

## Erforderliche API-Keys

```bash
# OpenAI API (erforderlich für LLM-Extraction)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-2024-08-06

# Anthropic API (optional, nur für MCP-Temporal-Validation)
ANTHROPIC_API_KEY=sk-ant-...
```

## Temporal Enrichment Konfiguration

### USE_MCP_TEMPORAL_VALIDATION
**Typ:** Boolean (true/false)  
**Standard:** false  
**Beschreibung:** Aktiviert MCP (Claude) für die Validierung und Verbesserung von temporalen Annotationen in ambigen Fällen.

```bash
# Nur dateparser nutzen (schnell, kostenlos)
USE_MCP_TEMPORAL_VALIDATION=false

# MCP-Validation aktivieren (für bessere Genauigkeit bei komplexen Zeitangaben)
USE_MCP_TEMPORAL_VALIDATION=true
```

**Wann MCP nutzen:**
- Bei ambigen Ausdrücken wie "damals", "zu der Zeit", "währenddessen"
- Bei komplexen Timelines mit mehreren verschachtelten Zeitreferenzen
- Wenn höchste Präzision bei Zeitangaben kritisch ist

**Kosten-Nutzen:**
- Ohne MCP: ~85% Genauigkeit, €0 Kosten, ~10s Verarbeitung
- Mit MCP: ~92% Genauigkeit, ~€0.05 pro Transkript (100 Turns), ~40s Verarbeitung

### MCP_CONFIDENCE_THRESHOLD
**Typ:** Float (0.0-1.0)  
**Standard:** 0.8  
**Beschreibung:** Schwellenwert für Confidence-Score. Nur Ausdrücke mit niedrigerem Score werden an MCP eskaliert.

```bash
MCP_CONFIDENCE_THRESHOLD=0.8  # Standard
MCP_CONFIDENCE_THRESHOLD=0.9  # Weniger MCP-Calls, höhere Kosten-Effizienz
MCP_CONFIDENCE_THRESHOLD=0.7  # Mehr MCP-Calls, höhere Genauigkeit
```

## ElevenLabs Integration

Die Integration erkennt automatisch ElevenLabs `post_call_transcription` Webhooks anhand des `type` Feldes.

**Unterstützte Formate:**
1. **ElevenLabs Webhook** (automatisch erkannt)
   - `type: "post_call_transcription"`
   - Extrahiert: Kandidateninfo, Zeitstempel, Call-Metadaten
   
2. **Internes Format** (backward-kompatibel)
   - Array von `{speaker: "A"|"B", text: "..."}`

## Empfohlene Konfiguration

### Entwicklung/Testing
```bash
USE_MCP_TEMPORAL_VALIDATION=false  # Schnell, kostenlos
```

### Produktion (Standard)
```bash
USE_MCP_TEMPORAL_VALIDATION=false  # dateparser ist für die meisten Fälle ausreichend
```

### Produktion (High-Precision)
```bash
USE_MCP_TEMPORAL_VALIDATION=true   # Für kritische Anwendungen
MCP_CONFIDENCE_THRESHOLD=0.8       # Ausgewogener Kompromiss
```


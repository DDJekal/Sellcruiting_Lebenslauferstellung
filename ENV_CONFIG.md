# Environment Variables für KI-Sellcruiting Pipeline

## Benötigte Environment Variables in Render:

```bash
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-2024-08-06

# Questionnaire API Configuration
HIRINGS_API_URL=https://your-api-domain.com
HIRING_API_TOKEN=your_hiring_api_token_here

# Optional: Anthropic für temporale Validierung
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# HOC API Configuration (3 separate endpoints)
# Verwendet dieselbe URL und denselben Token wie HIRINGS_API
HOC_API_URL=https://high-office.hirings.cloud/api/v1
HOC_API_KEY=your_hiring_api_token_here  # Derselbe Token wie HIRING_API_TOKEN

# Server Configuration
PORT=10000

# Optional: Protocol Template Fallback
DEFAULT_PROTOCOL_TEMPLATE_ID=63

# Optional: Temporal Validation
USE_MCP_TEMPORAL_VALIDATION=false
```

## Wichtig:

1. **HIRINGS_API_URL**: Basis-URL Ihrer API (z.B. `https://high-office.hirings.cloud/api/v1`)
2. **HIRING_API_TOKEN**: API-Token für Authentifizierung bei der Questionnaire-API
3. Die API muss den Endpoint `GET /api/v1/questionnaire/<campaign_id>` bereitstellen

## HOC API Integration:

Die HOC API verwendet **3 separate Endpunkte** zum Senden der Daten:
1. **POST /api/v1/campaigns/{campaign_id}/transcript/** - Gesprächsprotokoll (minimal, nur checked-Werte)
2. **POST /api/v1/applicants/resume** - Bewerber + Lebenslauf (vollständig)
3. **POST /api/v1/applicants/ai/call/meta** - ElevenLabs Metadata + Temporal Context

**Authorization**: Direkter Token ohne "Bearer" Präfix:
```python
headers = {"Authorization": token}  # NICHT: f"Bearer {token}"
```

**Empfohlene Konfiguration in Render**:
- `HOC_API_URL` = `https://high-office.hirings.cloud/api/v1` (gleiche Base-URL wie HIRINGS_API_URL)
- `HOC_API_KEY` = Derselbe Token wie `HIRING_API_TOKEN`

## Neue Features:

- Automatischer Abruf des Gesprächsprotokolls via `campaign_id` aus ElevenLabs Metadata
- Fallback zu lokalem Template wenn API nicht verfügbar
- Vollständige ElevenLabs Metadata-Extraktion (campaign_id, applicant_id, to_number, etc.)

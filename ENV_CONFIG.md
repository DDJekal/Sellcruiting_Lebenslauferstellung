# Environment Variables für KI-Sellcruiting Pipeline

## Benötigte Environment Variables in Render:

```bash
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-2024-08-06

# Questionnaire API Configuration
HIRINGS_API_URL=https://your-api-domain.com
WEBHOOK_API_KEY=your_webhook_api_key_here

# Optional: Anthropic für temporale Validierung
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Optional: HOC API
HOC_API_URL=
HOC_API_KEY=

# Server Configuration
PORT=10000

# Optional: Protocol Template Fallback
DEFAULT_PROTOCOL_TEMPLATE_ID=63

# Optional: Temporal Validation
USE_MCP_TEMPORAL_VALIDATION=false
```

## Wichtig:

1. **HIRINGS_API_URL**: Basis-URL Ihrer API (z.B. `https://api.example.com`)
2. **WEBHOOK_API_KEY**: API-Key für Authentifizierung bei der Questionnaire-API
3. Die API muss den Endpoint `GET /api/v1/questionnaire/<campaign_id>` bereitstellen

## Neue Features:

- Automatischer Abruf des Gesprächsprotokolls via `campaign_id` aus ElevenLabs Metadata
- Fallback zu lokalem Template wenn API nicht verfügbar
- Vollständige ElevenLabs Metadata-Extraktion (campaign_id, applicant_id, to_number, etc.)

# 🚀 Render Deployment Guide

## Webhook-Server für ElevenLabs → Pipeline → HOC

Dieses Dokument beschreibt, wie Sie den Webhook-Server auf Render deployen.

---

## 📋 Voraussetzungen

- ✅ GitHub Repository mit diesem Code
- ✅ Render Account (kostenlos: https://render.com)
- ✅ OpenAI API Key
- ✅ (Optional) Anthropic API Key für MCP

---

## 🔧 Deployment-Schritte

### 1. GitHub Push

```bash
git add .
git commit -m "Add webhook server and Render deployment config"
git push origin main
```

### 2. Render Dashboard Setup

1. **Gehen Sie zu:** https://dashboard.render.com
2. **Klicken Sie:** "New" → "Web Service"
3. **Verbinden Sie:** Ihr GitHub Repository
4. **Konfigurieren Sie:**
   - **Name:** `ki-sellcruiting-processor` (oder Ihre Wahl)
   - **Region:** Frankfurt (EU)
   - **Branch:** main
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn webhook_server:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Starter (kostenlos)

### 3. Environment Variables setzen

Gehen Sie zu **Environment** Tab und fügen Sie hinzu:

#### Erforderlich:
```
OPENAI_API_KEY=sk-proj-...
```

#### Optional:
```
ANTHROPIC_API_KEY=sk-ant-...
USE_MCP_TEMPORAL_VALIDATION=false
MCP_CONFIDENCE_THRESHOLD=0.8
DEFAULT_PROTOCOL_TEMPLATE_ID=63
```

#### Später (wenn HOC-Details verfügbar):
```
HOC_API_URL=https://hoc-api.example.com
HOC_API_KEY=your-hoc-api-key
```

### 4. Deploy

- Klicken Sie **"Create Web Service"**
- Render baut und deployed automatisch
- Nach ~5 Minuten: Service ist live! ✅

---

## 🌐 Ihre Webhook-URL

Nach dem Deployment erhalten Sie:

```
https://ki-sellcruiting-processor.onrender.com
```

**Für ElevenLabs konfigurieren:**
```
https://ki-sellcruiting-processor.onrender.com/elevenlabs/posthook
```

---

## 🔍 Endpoints

### Health Check
```
GET https://ki-sellcruiting-processor.onrender.com/health
```

Response:
```json
{
  "status": "healthy",
  "checks": {
    "openai_api_key": true,
    "anthropic_api_key": false,
    "hoc_api_configured": false
  }
}
```

### ElevenLabs Webhook
```
POST https://ki-sellcruiting-processor.onrender.com/elevenlabs/posthook
Content-Type: application/json

{
  "type": "post_call_transcription",
  "data": {
    "conversation_id": "conv_...",
    "transcript": [...]
  }
}
```

Response:
```json
{
  "status": "accepted",
  "conversation_id": "conv_...",
  "message": "Processing started in background"
}
```

---

## ⚙️ ElevenLabs Posthook konfigurieren

1. **ElevenLabs Dashboard** öffnen
2. **Agent Settings** → **Webhooks**
3. **Add Webhook:**
   - **URL:** `https://ki-sellcruiting-processor.onrender.com/elevenlabs/posthook`
   - **Event:** `post_call_transcription`
   - **Method:** POST
4. **Speichern**

### Test:
- Führen Sie einen Test-Call durch
- Überprüfen Sie Render Logs: `https://dashboard.render.com` → Ihr Service → Logs

---

## 📊 Monitoring

### Render Logs anzeigen:
```
Dashboard → Ihr Service → Logs
```

### Logs lokal testen:
```bash
# Installiere Dependencies
pip install -r requirements.txt

# Starte Server lokal
python webhook_server.py

# In anderem Terminal: Test-Request
curl -X POST http://localhost:8000/elevenlabs/posthook \
  -H "Content-Type: application/json" \
  -d @Input2/elevenlabs_webhook_test.json
```

---

## 🔄 Updates deployen

Render deployed automatisch bei jedem Git Push:

```bash
git add .
git commit -m "Your changes"
git push origin main
```

Render erkennt den Push und deployed automatisch! 🚀

---

## 🐛 Troubleshooting

### Build schlägt fehl?
- Prüfen Sie `requirements.txt`
- Prüfen Sie Python-Version (sollte 3.10+ sein)

### Server startet nicht?
- Prüfen Sie Logs in Render Dashboard
- Prüfen Sie Environment Variables (OPENAI_API_KEY gesetzt?)

### Webhook funktioniert nicht?
- Testen Sie Health-Endpoint: `https://ihr-service.onrender.com/health`
- Prüfen Sie ElevenLabs Webhook-Konfiguration
- Prüfen Sie Render Logs für Fehler

### HOC-Integration schlägt fehl?
- Setzen Sie `HOC_API_URL` und `HOC_API_KEY`
- Prüfen Sie HOC API-Dokumentation
- Passen Sie `hoc_client.py` bei Bedarf an

---

## 📚 Weitere Ressourcen

- **Render Docs:** https://render.com/docs
- **FastAPI Docs:** https://fastapi.tiangolo.com
- **ElevenLabs Webhooks:** https://elevenlabs.io/docs/api-reference/webhooks

---

## 🎯 Next Steps

1. ✅ Webhook-Server deployed
2. ⏳ ElevenLabs Posthook konfigurieren
3. ⏳ Test-Call durchführen
4. ⏳ HOC API-Details erhalten
5. ⏳ HOC-Integration vervollständigen

**Status:** Ready for ElevenLabs integration! 🚀


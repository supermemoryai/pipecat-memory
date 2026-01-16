# Pipecat + Supermemory Voice Demo - Deployment Guide

## Architecture

```
┌─────────────────────────┐      ┌─────────────────────────┐
│  Cloudflare Workers     │      │  Railway                │
│  ───────────────────    │      │  ───────────────────    │
│  Frontend (Vite/React)  │─────▶│  Python Backend         │
│  - Voice UI             │  WS  │  - Pipecat pipeline     │
│  - Memories API proxy   │      │  - STT/LLM/TTS          │
└─────────────────────────┘      └─────────────────────────┘
```

## Prerequisites

- Node.js 18+
- Python 3.11+
- Cloudflare account
- Railway account
- OpenAI API key
- Supermemory API key

## 1. Deploy Backend to Railway

### Option A: Deploy via Railway CLI

```bash
cd backend

# Login to Railway
railway login

# Create new project
railway init

# Set environment variables
railway variables set OPENAI_API_KEY=sk-...
railway variables set SUPERMEMORY_API_KEY=sm-...
railway variables set WS_HOST=your-project.railway.app
railway variables set USE_SSL=true
railway variables set ALLOWED_ORIGINS=https://your-frontend.pages.dev

# Deploy
railway up
```

### Option B: Deploy via GitHub

1. Push the `backend/` folder to a GitHub repo
2. Connect Railway to the repo
3. Railway will auto-detect the Dockerfile
4. Set environment variables in Railway dashboard

### Environment Variables (Backend)

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for STT/LLM/TTS |
| `SUPERMEMORY_API_KEY` | Yes | Supermemory API key |
| `PORT` | No | Server port (Railway sets this) |
| `WS_HOST` | Yes | Your Railway domain (e.g., `app.railway.app`) |
| `USE_SSL` | Yes | Set to `true` for production |
| `ALLOWED_ORIGINS` | No | CORS origins (default: `*`) |

### Verify Backend

```bash
# Health check
curl https://your-backend.railway.app/health

# Should return: {"status":"ok","provider":"supermemory","version":"1.0.0"}
```

## 2. Deploy Frontend to Cloudflare Workers

### Setup

```bash
# Install dependencies
npm install

# Create .env file
cp .env.example .env

# Edit .env with your Railway backend URL
# VITE_BACKEND_URL=https://your-backend.railway.app
```

### Local Development

```bash
# Start backend locally (in backend/ folder)
cd backend
pip install -r requirements.txt
python server.py

# In another terminal, start frontend
npm run dev

# Open http://localhost:5173
```

### Deploy to Cloudflare

```bash
# Login to Cloudflare (if not already)
npx wrangler login

# Deploy
npm run deploy
```

### Environment Variables (Frontend)

Set in `.env` file or Cloudflare dashboard:

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_BACKEND_URL` | Yes | Railway backend URL |
| `SUPERMEMORY_API_KEY` | Yes | For memories API (set in `.dev.vars` or Cloudflare) |

## 3. Testing the Demo

1. Open the frontend URL
2. Click the green circle to start a conversation
3. Allow microphone access
4. Speak to the voice assistant
5. Watch memories appear in the right panel

## Troubleshooting

### WebSocket Connection Fails

- Check that `VITE_BACKEND_URL` is correct (no trailing slash)
- Ensure Railway deployment is running
- Check CORS settings (`ALLOWED_ORIGINS`)
- Verify `WS_HOST` matches your Railway domain

### No Audio Output

- Check browser console for errors
- Ensure microphone permission is granted
- Try refreshing the page

### Memories Not Loading

- Check `SUPERMEMORY_API_KEY` is set correctly
- Verify the userId is being passed to the backend

## Local Development Tips

### Run Both Services

Terminal 1 (Backend):
```bash
cd backend
python server.py
```

Terminal 2 (Frontend):
```bash
npm run dev
```

### Test with Different Users

The app generates a unique userId per browser. To test with a fresh user:
1. Open browser DevTools
2. Application > Local Storage
3. Delete `pipecat-userId`
4. Refresh the page

## Architecture Notes

### Multi-User Support

- Each user gets a unique `userId` stored in localStorage
- Backend uses `userId` as `containerTag` for Supermemory
- Sessions are isolated per user

### Voice Pipeline

```
Browser Mic → WebSocket → Pipecat Server
                              ↓
                        Silero VAD (voice detection)
                              ↓
                        OpenAI Whisper (STT)
                              ↓
                        Supermemory (context)
                              ↓
                        GPT-4o-mini (LLM)
                              ↓
                        OpenAI TTS
                              ↓
                        WebSocket → Browser Speaker
```

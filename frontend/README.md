# Conversational AI Frontend (React)

React + Vite version of the Ollama WebSocket chat UI. API and routes are unchanged: WebSocket `ws://localhost:8000/ws/chat`, same message types and payloads.

## Local development

```bash
cd frontend
npm install
npm run dev
```

Ensure the FastAPI backend is running on port 8000.

## Deploy to Vercel

1. In Vercel, set **Root Directory** to `frontend` (or deploy from inside the `frontend` folder).
2. Build and output are already set: **Build Command** `npm run build`, **Output Directory** `dist`.
3. Deploy. The app will load the frontend; the WebSocket still uses `ws://localhost:8000/ws/chat` (update to your backend URL in production if needed).

## Reset session

In the browser console: `window.__resetSession()` (same as the original HTML app).

## Conversational AI System – UniGuide Admissions Assistant

This project implements a fully local, production-style conversational AI system for a **university admissions inquiry assistant** (“UniGuide”). It is designed for low-latency CPU inference, real-time streaming, and concurrent users, using only prompt orchestration and conversational memory (no tools, agents, or RAG).

### 1. Business Use-Case

**Use-case**: A prospective student conversational assistant that answers questions about:
- Admissions requirements and deadlines
- Programs and majors
- Tuition, scholarships, and financial-aid concepts
- Campus life, housing, and student services

**Tone & policies**:
- Warm, professional, and encouraging
- Does not invent concrete URLs, email addresses, or phone numbers
- Gives generic guidance when university-specific details vary
- Avoids giving legal, immigration, or binding financial advice; instead, recommends official channels

**Example dialogue (abridged)**:
- **User**: “What GPA do I need to get into the CS program?”
- **UniGuide**: Explains that GPA thresholds vary, describes typical competitive ranges and other holistic factors, and suggests checking official program pages.

### 2. Architecture Overview

High-level architecture:

```mermaid
flowchart LR
  UI[Web UI (frontend.html)] <-- WebSocket (JSON) --> API[FastAPI Backend]
  API <-- in-memory state --> CM[Conversation Manager]
  API <-- streaming tokens --> LLM[Local LLM Engine (Ollama)]
```

Components:
- **Frontend**: `frontend.html` – ChatGPT-style UI over WebSocket.
- **Backend API**: `backend/main.py` – FastAPI app with REST + WebSocket endpoints.
- **Conversation Manager**: `conversation_manager/manager.py` – session handling, history management, prompt orchestration.
- **LLM Engine**: `llm_engine.py` – wrapper around local Ollama model using streaming.

The backend itself is **stateless across processes**; conversational state lives in an in-memory manager keyed by `session_id`.

### 3. Local LLM Selection & Optimization

- **Model family**: Phi-series, small instruction-tuned model suitable for CPU.
- **Serving runtime**: Ollama running locally.
- **Quantization**: Use an appropriate quantized Phi variant configured inside Ollama.

**Context memory management**:
- Conversation state is stored as a list of `{role, content}` messages per session.
- `ConversationManager` keeps:
  - 1 system message (domain policy and tone)
  - Up to `max_messages` total messages (default: 32)
  - If exceeded, older non-system messages are truncated while preserving system instructions and the most recent turns.

You can tune `max_messages` based on your model’s context window and latency goals.

**Latency benchmarking (how to run)**:
- Use the REST endpoint for stable measurements:
  - `POST /api/chat` with a fixed prompt (e.g., “Explain undergraduate admissions in 3 bullets.”).
  - Measure total response time via Postman / `curl` + `time`.
- Collect:
  - Mean / P50 / P90 latency over ~20–50 runs.
  - CPU utilization from your OS tools (e.g., Task Manager on Windows).

### 4. Conversation Manager & Prompt Orchestration

Located in `conversation_manager/manager.py`, the `ConversationManager`:
- Generates a **system prompt** describing UniGuide’s role, tone, and constraints.
- Manages sessions using random UUIDs.
- Maintains `SessionState` objects with:
  - `session_id`
  - `messages` (system + user + assistant messages)
  - Timestamps for basic TTL eviction.
- Enforces a simple **context window** policy by truncating old messages.

Prompt orchestration:
- For each turn:
  1. Register user message in the session.
  2. Build the prompt: `[system, user, assistant, ..., latest user]`.
  3. Send to the LLM engine as a standard chat-style message list.
  4. Stream assistant tokens back and persist the final assistant reply.

### 5. Backend API (FastAPI)

File: `backend/main.py`

**Endpoints**:
- `GET /health`
  - Returns `{ "status": "ok", "model": "<model-name>" }`.
- `POST /api/chat`
  - Request body:
    ```json
    {
      "session_id": "optional-or-null",
      "message": "user message text",
      "reset_session": false
    }
    ```
  - Response:
    ```json
    {
      "session_id": "<resolved-session-id>",
      "reply": "assistant reply text"
    }
    ```
- `WEBSOCKET /ws/chat`
  - JSON event protocol:
    - Client → Server:
      - Start or continue a chat:
        ```json
        {
          "type": "message",
          "payload": {
            "session_id": "<optional>",
            "message": "Hello, UniGuide!"
          }
        }
        ```
      - Reset session:
        ```json
        {
          "type": "reset",
          "session_id": "<optional>"
        }
        ```
      - Ping:
        ```json
        { "type": "ping", "session_id": "<optional>" }
        ```
    - Server → Client:
      - Start of assistant streaming:
        ```json
        { "type": "start", "session_id": "<id>" }
        ```
      - Streamed chunk:
        ```json
        { "type": "chunk", "session_id": "<id>", "content": "partial text" }
        ```
      - End of streaming:
        ```json
        { "type": "end", "session_id": "<id>" }
        ```
      - Session reset:
        ```json
        { "type": "session_reset", "session_id": "<new-id>" }
        ```
      - Error:
        ```json
        { "type": "error", "error": "description here", "session_id": "<optional>" }
        ```

Concurrency:
- FastAPI + Uvicorn handle concurrent WebSocket and REST requests asynchronously.
- The in-memory conversation manager and LLM streaming are non-blocking per connection (within the limits of the Python process and CPU).

### 6. LLM Engine

File: `llm_engine.py`

Responsibilities:
- Provide `stream_chat_completion(messages)` to stream text chunks from Ollama.
- Provide `complete_chat(messages)` to aggregate chunks into a single string.
- Isolates Ollama-specific HTTP streaming details from the rest of the app.

Environment variables:
- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `OLLAMA_MODEL` (default: `phi3`)

### 7. Web UI

File: `frontend.html`

Features:
- Single-page chat UI with:
  - Real-time WebSocket messaging
  - Streaming responses
  - Conversation history within the page
- `session_id` is persisted in `localStorage` (`uniguide_session_id`) so the same browser tab continues the same session.
- Supports a programmatic reset via `window.__resetSession()` (can be bound to a button if desired).

The UI communicates with the backend using the JSON WebSocket protocol described above.

### 8. Dockerized Deployment

File: `Dockerfile-app`

Build and run:

```bash
docker build -t uniguide-backend -f Dockerfile-app .
docker run --rm -p 8000:8000 --name uniguide uniguide-backend
```

Make sure **Ollama** is running on the host (and accessible from the container). For a simple local setup, it is often easiest to:
- Run Ollama on the host (`ollama serve`).
- Run the container with `--network host` on Linux, or use appropriate port mapping on other OSes and set `OLLAMA_BASE_URL` accordingly.

### 9. Postman Collection

File: `postman_collection.json`

Contains:
- `Health Check` – `GET /health`
- `Chat (REST)` – `POST /api/chat`

You can import this file into Postman to manually test the API and measure latency.

### 10. Setup & Run Instructions

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Run Ollama with a Phi model**:
   ```bash
   ollama pull phi3        # or another Phi variant
   ollama serve
   # Optionally:
   # set OLLAMA_MODEL=phi3
   ```
3. **Start the FastAPI backend**:
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
4. **Open the web UI**:
   - Open `frontend.html` directly in a browser, or
   - Serve it via a simple static file server (e.g., `python -m http.server`) and browse to it.

### 11. Performance & Evaluation (Guidelines)

For assignment reporting:
- **Latency benchmarking**:
  - Use `POST /api/chat` with a fixed prompt, collect timing statistics in Postman or via scripts.
  - Record P50/P90 latencies for different prompt lengths and concurrent clients.
- **Stress testing**:
  - Use a load-testing tool (e.g., `locust`, `k6`, or `ab` for REST) to simulate multiple users.
  - Observe CPU usage, memory footprint, and failure behavior when the machine is saturated.
- **Failure handling**:
  - Document behavior if Ollama is down (502 from REST, `error` events in WebSocket).
  - Note any timeouts or back-pressure strategies you adopt.

### 12. Known Limitations

- In-memory session storage means state is lost on process restart and does not scale across multiple instances without an external store.
- Latency and throughput are bounded by CPU-only inference performance of the local LLM.
- No tools, plugins, or RAG are used by design; the assistant’s answers are limited to model prior and prompt context.


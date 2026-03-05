from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from conversation_manager.manager import conversation_manager
from llm_engine import OLLAMA_MODEL, complete_chat, stream_chat_completion


app = FastAPI(title="Conversational AI WebSocket Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    reset_session: bool = False


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    await websocket.accept()

    while True:
        try:
            raw = await websocket.receive_json()
        except WebSocketDisconnect:
            break

        event_type: str = raw.get("type", "message")

        if event_type == "ping":
            await websocket.send_json({"type": "pong"})
            continue

        if event_type == "reset":
            session_id = raw.get("session_id") or conversation_manager.new_session_id()
            conversation_manager.reset_session(session_id)
            await websocket.send_json(
                {
                    "type": "session_reset",
                    "session_id": session_id,
                }
            )
            continue

        if event_type != "message":
            await websocket.send_json(
                {
                    "type": "error",
                    "error": f"Unsupported event type: {event_type}",
                }
            )
            continue

        payload: Dict[str, Any] = raw.get("payload") or {}
        message_text: str = payload.get("message") or ""
        session_id: str = payload.get("session_id") or ""

        if not message_text:
            await websocket.send_json(
                {
                    "type": "error",
                    "error": "Missing 'message' in payload.",
                }
            )
            continue

        if not session_id:
            session_id = conversation_manager.new_session_id()

        conversation_manager.register_user_message(session_id, message_text)
        messages = conversation_manager.build_prompt(session_id)

        await websocket.send_json(
            {
                "type": "start",
                "session_id": session_id,
            }
        )

        collected_chunks: List[str] = []

        try:
            async for chunk in stream_chat_completion(messages):
                collected_chunks.append(chunk)
                await websocket.send_json(
                    {
                        "type": "chunk",
                        "session_id": session_id,
                        "content": chunk,
                    }
                )
        except Exception as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "session_id": session_id,
                    "error": f"LLM engine error: {exc}",
                }
            )
            continue

        assistant_reply = "".join(collected_chunks)

        if assistant_reply:
            conversation_manager.register_assistant_message(
                session_id, assistant_reply
            )

        await websocket.send_json(
            {
                "type": "end",
                "session_id": session_id,
            }
        )


@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok", "model": OLLAMA_MODEL}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or conversation_manager.new_session_id()

    if request.reset_session:
        conversation_manager.reset_session(session_id)

    conversation_manager.register_user_message(session_id, request.message)
    messages = conversation_manager.build_prompt(session_id)

    try:
        reply = await complete_chat(messages)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM engine error: {exc}",
        ) from exc

    conversation_manager.register_assistant_message(session_id, reply)
    return ChatResponse(session_id=session_id, reply=reply)

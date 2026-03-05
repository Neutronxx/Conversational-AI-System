from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Literal, TypedDict


Role = Literal["system", "user", "assistant"]


class Message(TypedDict):
    role: Role
    content: str


@dataclass
class SessionState:
    session_id: str
    messages: List[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class ConversationManager:
    """In-memory conversation manager for multi-user chat sessions.

    This manager:
    - Maintains per-session dialogue history.
    - Enforces system policies and domain constraints.
    - Builds structured prompts for the LLM.
    - Applies simple context window management via max message count.
    """

    def __init__(
        self,
        *,
        max_messages: int = 32,
        session_ttl_seconds: int = 60 * 60,
    ) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._max_messages = max_messages
        self._session_ttl_seconds = session_ttl_seconds

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    def new_session_id(self) -> str:
        return str(uuid.uuid4())

    def _get_or_create_session(self, session_id: str) -> SessionState:
        now = time.time()
        self._evict_expired(now)

        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(
                session_id=session_id,
                messages=[self._system_message()],
            )

        state = self._sessions[session_id]
        state.updated_at = now
        return state

    def reset_session(self, session_id: str) -> None:
        self._sessions[session_id] = SessionState(
            session_id=session_id,
            messages=[self._system_message()],
        )

    def _evict_expired(self, now: float) -> None:
        ttl = self._session_ttl_seconds
        to_delete = [
            sid
            for sid, state in self._sessions.items()
            if now - state.updated_at > ttl
        ]
        for sid in to_delete:
            self._sessions.pop(sid, None)

    # ------------------------------------------------------------------
    # Domain-specific prompt orchestration
    # ------------------------------------------------------------------
    @staticmethod
    def _system_message() -> Message:
        """System prompt for a University Admissions Assistant."""
        content = (
            "You are UniGuide, a helpful, concise university admissions "
            "assistant for a mid‑sized university.\n\n"
            "Primary goals:\n"
            "1. Answer questions about admissions requirements, deadlines, "
            "   scholarships, tuition, programs, and campus life.\n"
            "2. Ask clarifying questions when information is ambiguous.\n"
            "3. Keep responses under 6 sentences unless the user explicitly "
            "   asks for more detail.\n\n"
            "Policies and constraints:\n"
            "- DO NOT invent specific URLs, email addresses, or phone numbers; "
            "  instead, say that exact contact details may vary by institution.\n"
            "- If the user asks about another university, answer in generic "
            "  terms and remind them that policies differ by institution.\n"
            "- Do not make up legal, visa, or financial advice. Encourage "
            "  users to consult official sources for those.\n"
            "- If you are unsure, say so explicitly and give a safe, general "
            "  guideline.\n\n"
            "Tone:\n"
            "- Warm, professional, and encouraging.\n"
            "- Write in clear, plain language.\n"
            "- Use bullet points for multi-part answers when helpful.\n\n"
            "Important implementation notes:\n"
            "- You do NOT have tools, browsing, or external data access.\n"
            "- You do NOT have retrieval-augmented generation. Rely only on "
            "  the conversation history and your internal knowledge.\n"
            "- Maintain continuity with previous turns and avoid repeating "
            "  long instructions verbatim on every reply."
        )
        return {"role": "system", "content": content}

    def register_user_message(self, session_id: str, content: str) -> None:
        state = self._get_or_create_session(session_id)
        state.messages.append({"role": "user", "content": content})
        self._truncate_if_needed(state)

    def register_assistant_message(self, session_id: str, content: str) -> None:
        state = self._get_or_create_session(session_id)
        state.messages.append({"role": "assistant", "content": content})
        self._truncate_if_needed(state)

    def _truncate_if_needed(self, state: SessionState) -> None:
        """Simple context management: keep system + last N turns."""
        if len(state.messages) <= self._max_messages:
            return

        system_msgs = [m for m in state.messages if m["role"] == "system"]
        non_system = [m for m in state.messages if m["role"] != "system"]
        keep_tail = non_system[-(self._max_messages - 1) :]

        state.messages = system_msgs[:1] + keep_tail

    def build_prompt(self, session_id: str) -> List[Message]:
        """Return the messages to send to the LLM."""
        state = self._get_or_create_session(session_id)
        return list(state.messages)


# Singleton-style manager instance for the FastAPI app to import.
conversation_manager = ConversationManager()


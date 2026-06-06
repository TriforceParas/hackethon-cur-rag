from app.db.models import ChatMode
from app.services.llm_service import LLMService


class RouterService:
    """Chooses exactly one tool mode for each user message."""

    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    def route(self, message: str, history: list[dict] | None = None) -> tuple[ChatMode, str]:
        deterministic_mode = self.preferred_deterministic_mode(message, history or [])
        if deterministic_mode:
            return deterministic_mode

        prompt = self._build_router_prompt(message, history or [])
        try:
            raw = self.llm_service.generate(
                prompt,
                system_prompt="You are a strict router. Return JSON only and no markdown.",
            )
            parsed = self.llm_service.parse_json_response(raw)
            mode_value = parsed.get("mode") if parsed else None
            reason = parsed.get("reason", "LLM router decision") if parsed else "LLM router failed"
            if mode_value in {mode.value for mode in ChatMode}:
                return ChatMode(mode_value), reason
        except Exception:
            pass

        return self._fallback_route(message, history or [])

    def preferred_deterministic_mode(self, message: str, history: list[dict]) -> tuple[ChatMode, str] | None:
        """High-confidence rules that should override the LLM router."""
        text = message.lower().strip()

        if self.is_current_or_live_query(text):
            return ChatMode.WEB_SEARCH, "High-confidence current/live query"
        if history and self.is_memory_followup(text):
            return ChatMode.MEMORY_CONTEXT, "High-confidence memory follow-up"
        if self.is_document_query(text):
            return ChatMode.RAG, "High-confidence document query"
        return None

    @staticmethod
    def is_current_or_live_query(text: str) -> bool:
        web_terms = [
            "latest",
            "current",
            "today",
            "todays",
            "today's",
            "recent",
            "news",
            "live",
            "breaking",
            "stock",
            "market",
            "price",
            "prices",
            "weather",
            "trend",
            "trending",
            "now",
            "this week",
            "this month",
            "2026",
        ]
        return any(term in text for term in web_terms)

    @staticmethod
    def is_document_query(text: str) -> bool:
        rag_terms = [
            "uploaded",
            "document",
            "documents",
            "pdf",
            "file",
            "report",
            "proposal",
            "policy",
            "handbook",
            "manual",
            "from the file",
            "from the pdf",
            "from the document",
            "summarize the uploaded",
        ]
        return any(term in text for term in rag_terms)

    @staticmethod
    def is_memory_followup(text: str) -> bool:
        memory_terms = [
            "that",
            "it",
            "this",
            "they",
            "those",
            "continue",
            "again",
            "previous",
            "what about",
            "who created it",
            "summarize what we discussed",
        ]
        return len(text.split()) <= 8 or any(term in text for term in memory_terms)

    def _build_router_prompt(self, message: str, history: list[dict]) -> str:
        recent = "\n".join(f"{item['role']}: {item['content']}" for item in history[-6:])
        return f"""
Classify the user message into exactly one category.

GENERAL_CHAT: general knowledge, explanation, coding help, simple reasoning, or no external data needed.
RAG: asks about uploaded documents, PDFs, files, policies, reports, handbooks, proposals, or internal knowledge.
WEB_SEARCH: asks about latest, current, today, recent, news, live, stock market, prices, trends, or changeable facts.
MEMORY_CONTEXT: depends on previous conversation, pronouns, "explain that again", "what about it?", "who created it?", summaries, or continuations.
HYBRID: combines tools when the question explicitly asks to compare, combine, or relate uploaded documents with current web information or previous context.

Recent conversation:
{recent or "(none)"}

User message: {message}

Return JSON only:
{{"mode": "GENERAL_CHAT", "reason": "brief reason"}}
"""

    def _fallback_route(self, message: str, history: list[dict]) -> tuple[ChatMode, str]:
        text = message.lower().strip()
        if self.is_current_or_live_query(text):
            return ChatMode.WEB_SEARCH, "Keyword fallback matched changeable/current information"
        if self.is_document_query(text):
            return ChatMode.RAG, "Keyword fallback matched document-oriented request"
        if history and self.is_memory_followup(text):
            return ChatMode.MEMORY_CONTEXT, "Keyword fallback matched follow-up or pronoun-dependent request"
        return ChatMode.GENERAL_CHAT, "Keyword fallback selected general chat"

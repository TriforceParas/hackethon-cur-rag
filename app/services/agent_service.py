from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.db.models import ChatMode
from app.schemas.chat import ChatResponse
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.router_service import RouterService
from app.services.web_search_service import WebSearchService


@dataclass
class AgentPlan:
    mode: ChatMode
    tools: list[str]
    reason: str
    memory_used: bool = False


class AgentService:
    """Lightweight agent orchestrator for planning, tool execution, and synthesis."""

    def __init__(
        self,
        llm_service: LLMService,
        memory_service: MemoryService,
        router_service: RouterService,
        rag_service: RAGService,
        web_search_service: WebSearchService,
        settings: Settings | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.router_service = router_service
        self.rag_service = rag_service
        self.web_search_service = web_search_service
        self.settings = settings or get_settings()

    def run(self, session_id: str | None, message: str) -> ChatResponse:
        """Run the full agent workflow for one chat request."""
        sid = self.memory_service.ensure_session(session_id)
        history = self.memory_service.get_last_messages(sid, limit=10)
        self.memory_service.save_message(sid, "user", message)

        plan = self.plan(message, history)
        answer, sources = self.execute_plan(plan, message, history)

        self.memory_service.save_message(sid, "assistant", answer, plan.mode.value)
        return ChatResponse(
            session_id=sid,
            mode=plan.mode.value,
            answer=answer,
            sources=sources,
            memory_used=plan.memory_used,
            tools_used=plan.tools,
        )

    def plan(self, message: str, history: list[dict[str, Any]]) -> AgentPlan:
        """Create a conservative tool plan. High-confidence rules override LLM routing."""
        text = message.lower().strip()
        has_documents = self.memory_service.has_documents()
        is_current = self.router_service.is_current_or_live_query(text)
        is_document = self.router_service.is_document_query(text)
        is_memory = bool(history) and self.router_service.is_memory_followup(text)
        is_ambiguous_document = has_documents and self._looks_document_ambiguous(text)

        if has_documents and is_current and (is_document or is_ambiguous_document or self._asks_for_comparison(text)):
            tools = ["memory"] if is_memory else []
            tools.extend(["rag", "web_search"])
            return AgentPlan(ChatMode.HYBRID, tools, "Question needs uploaded documents and current web data", is_memory)

        if is_current:
            tools = ["memory", "web_search"] if is_memory else ["web_search"]
            mode = ChatMode.HYBRID if is_memory else ChatMode.WEB_SEARCH
            return AgentPlan(mode, tools, "Current/live query should use web search", is_memory)

        if is_memory and (is_document or is_ambiguous_document):
            return AgentPlan(ChatMode.HYBRID, ["memory", "rag"], "Follow-up requires memory and documents", True)

        if is_memory:
            return AgentPlan(ChatMode.MEMORY_CONTEXT, ["memory"], "Follow-up question requires memory", True)

        if has_documents and (is_document or is_ambiguous_document):
            return AgentPlan(ChatMode.RAG, ["rag"], "Question is likely answerable from uploaded documents")

        mode, reason = self.router_service.route(message, history)
        return AgentPlan(mode, self._tools_for_mode(mode), reason, mode == ChatMode.MEMORY_CONTEXT and bool(history))

    def execute_plan(
        self,
        plan: AgentPlan,
        message: str,
        history: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        if plan.mode == ChatMode.HYBRID:
            return self._answer_hybrid(plan, message, history)
        if plan.mode == ChatMode.RAG:
            answer, sources = self.rag_service.answer(message, min_score=self.settings.rag_min_score)
            if sources:
                return answer, self._tag_sources(sources, "rag")
            fallback_mode = ChatMode.WEB_SEARCH if self.router_service.is_current_or_live_query(message.lower()) else ChatMode.GENERAL_CHAT
            return self.execute_plan(AgentPlan(fallback_mode, self._tools_for_mode(fallback_mode), "RAG had no relevant chunks"), message, history)
        if plan.mode == ChatMode.WEB_SEARCH:
            answer, sources = self.web_search_service.search_and_answer(message)
            return answer, self._tag_sources(sources, "web_search")
        if plan.mode == ChatMode.MEMORY_CONTEXT:
            return self._answer_with_memory(message, history), []
        return self._answer_general(message, history), []

    def _answer_hybrid(
        self,
        plan: AgentPlan,
        message: str,
        history: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        evidence: list[str] = []
        sources: list[dict[str, Any]] = []

        if "memory" in plan.tools:
            memory_text = self._format_history(history)
            if memory_text:
                evidence.append(f"Conversation memory:\n{memory_text}")

        if "rag" in plan.tools:
            rag_answer, rag_sources = self.rag_service.answer(message, min_score=self.settings.rag_min_score)
            if rag_sources:
                evidence.append(f"Uploaded document findings:\n{rag_answer}")
                sources.extend(self._tag_sources(rag_sources, "rag"))

        if "web_search" in plan.tools:
            web_answer, web_sources = self.web_search_service.search_and_answer(message)
            if web_sources:
                evidence.append(f"Current web findings:\n{web_answer}")
                sources.extend(self._tag_sources(web_sources, "web_search"))

        if not evidence:
            return self._answer_general(message, history), []

        prompt = f"""
You are an AI agent combining multiple tool results.
Answer the user clearly and concisely.
Use only the evidence below.
Mention when information comes from uploaded documents versus current web results.

User question:
{message}

Evidence:
{chr(10).join(evidence)}
"""
        try:
            answer = self.llm_service.generate(prompt)
        except Exception:
            answer = "I combined the available tool results:\n\n" + "\n\n".join(evidence)

        return answer, sources

    def _answer_general(self, message: str, history: list[dict[str, Any]]) -> str:
        history_text = self._format_history(history)
        prompt = f"""
Answer the user clearly and concisely.
Use the previous conversation only if it is helpful.

Previous conversation:
{history_text or "(none)"}

User question:
{message}
"""
        try:
            return self.llm_service.generate(prompt)
        except Exception as exc:
            return self._fallback_general(message, history, exc)

    def _answer_with_memory(self, message: str, history: list[dict[str, Any]]) -> str:
        history_text = self._format_history(history)
        prompt = f"""
Answer the user's follow-up using the previous conversation context.
Resolve pronouns like it, this, that, they, and those from the conversation when possible.
If the previous context is insufficient, say what is missing.

Previous conversation:
{history_text or "(none)"}

Follow-up question:
{message}
"""
        try:
            return self.llm_service.generate(prompt)
        except Exception:
            return self._fallback_from_history(message, history, prefix="I used the previous conversation context.")

    def _fallback_general(self, message: str, history: list[dict[str, Any]], exc: Exception) -> str:
        text = message.lower().strip()
        if text in {"hi", "hello", "hey", "hii", "hola"}:
            return "Hello. I am ready to help with general questions, uploaded documents, latest web information, or follow-up context."

        if history:
            return self._fallback_from_history(
                message,
                history,
                prefix="I could not get a fresh LLM answer, but I can still use recent context.",
            )

        if self.router_service.is_current_or_live_query(text):
            answer, sources = self.web_search_service.search_and_answer(message)
            if sources:
                return answer

        return (
            "I could not generate an answer because the configured LLM provider returned empty output. "
            "Please check the LLM settings or switch to a reliable generation provider such as Groq for the demo."
        )

    def _fallback_from_history(self, message: str, history: list[dict[str, Any]], prefix: str) -> str:
        if not history:
            return f"{prefix} There is no previous conversation context available."

        text = message.lower()
        last_user = self._last_content(history, "user")
        last_assistant = self._last_content(history, "assistant")

        if "who created" in text or "who made" in text or "who developed" in text:
            target = self._infer_last_subject(last_user, last_assistant)
            if target:
                return (
                    f"{prefix} Your follow-up appears to refer to {target}. "
                    "Based on the previous conversation, please check the last assistant response above for the creator/developer detail."
                )

        if "summarize" in text or "what did we discuss" in text:
            return f"{prefix} Here is the recent conversation:\n\n{self._format_history(history)}"

        if "again" in text or "repeat" in text or "explain that" in text:
            if last_assistant:
                return f"{prefix} Here is the previous answer again:\n\n{last_assistant}"

        recent = []
        for item in history[-4:]:
            role = item.get("role", "message")
            content = " ".join(str(item.get("content", "")).split())
            if content:
                recent.append(f"- {role}: {content}")

        return (
            f"{prefix} I could not get a fresh LLM answer, but I found this recent context:\n\n"
            + "\n".join(recent)
        )

    @staticmethod
    def _last_content(history: list[dict[str, Any]], role: str) -> str:
        for item in reversed(history):
            if item.get("role") == role and item.get("content"):
                return str(item["content"])
        return ""

    @staticmethod
    def _infer_last_subject(last_user: str, last_assistant: str) -> str:
        candidates = [last_user, last_assistant]
        known_terms = ["LangGraph", "FastAPI", "Ollama", "Groq", "FAISS", "ChromaDB", "Streamlit"]
        combined = " ".join(candidates)
        for term in known_terms:
            if term.lower() in combined.lower():
                return term

        words = [word.strip(".,:;!?()[]{}") for word in last_user.split()]
        title_words = [word for word in words if len(word) > 2 and word[:1].isupper()]
        if title_words:
            return " ".join(title_words[:3])
        return ""

    @staticmethod
    def _format_history(history: list[dict[str, Any]]) -> str:
        return "\n".join(f"{item['role']}: {item['content']}" for item in history[-10:])

    @staticmethod
    def _tag_sources(sources: list[dict[str, Any]], tool: str) -> list[dict[str, Any]]:
        return [{**source, "tool": tool} for source in sources]

    @staticmethod
    def _tools_for_mode(mode: ChatMode) -> list[str]:
        if mode == ChatMode.RAG:
            return ["rag"]
        if mode == ChatMode.WEB_SEARCH:
            return ["web_search"]
        if mode == ChatMode.MEMORY_CONTEXT:
            return ["memory"]
        if mode == ChatMode.HYBRID:
            return ["rag", "web_search"]
        return ["llm"]

    @staticmethod
    def _looks_document_ambiguous(text: str) -> bool:
        ambiguous_terms = {
            "details",
            "summary",
            "summarize",
            "key points",
            "requirements",
            "rules",
            "eligibility",
            "deadline",
            "schedule",
            "rounds",
            "team size",
        }
        return any(term in text for term in ambiguous_terms)

    @staticmethod
    def _asks_for_comparison(text: str) -> bool:
        comparison_terms = {"compare", "relate", "combine", "contrast", "align", "against", "with latest"}
        return any(term in text for term in comparison_terms)

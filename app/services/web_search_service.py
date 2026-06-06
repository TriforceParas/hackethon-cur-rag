from typing import Any
import logging

from app.core.config import Settings, get_settings
from app.services.llm_service import LLMService


logger = logging.getLogger(__name__)


class WebSearchService:
    """Web search plus LLM summarization."""

    def __init__(self, llm_service: LLMService, settings: Settings | None = None) -> None:
        self.llm_service = llm_service
        self.settings = settings or get_settings()

    def search_and_answer(self, question: str) -> tuple[str, list[dict[str, Any]]]:
        try:
            raw_results = self._search(question)
        except Exception as exc:
            logger.exception("Web search failed")
            message = "I could not complete web search right now."
            if self.settings.debug_errors:
                message = f"{message} Details: {exc}"
            return message, []

        sources = [
            {
                "title": item.get("title") or item.get("body", "")[:80],
                "url": item.get("href"),
                "snippet": item.get("body"),
            }
            for item in raw_results
            if item.get("href")
        ]
        if not sources:
            return "I could not complete web search right now.", []

        source_text = "\n\n".join(
            f"{index}. {source['title']}\nURL: {source['url']}\nSnippet: {source.get('snippet') or ''}"
            for index, source in enumerate(sources, start=1)
        )
        prompt = f"""
Answer the user question using only these web search results.
Be concise. Do not hallucinate facts not present in the snippets.
Mention source titles where useful.

User question:
{question}

Search results:
{source_text}
"""
        try:
            answer = self.llm_service.generate(prompt)
        except Exception as exc:
            logger.warning("LLM could not summarize web results: %s", exc)
            answer = self._build_search_fallback(sources)

        return answer, [{"title": source["title"], "url": source["url"]} for source in sources]

    def _build_search_fallback(self, sources: list[dict[str, Any]]) -> str:
        lines = ["I found these current web results:"]
        for index, source in enumerate(sources[:5], start=1):
            snippet = " ".join(str(source.get("snippet") or "").split())
            if len(snippet) > 220:
                snippet = f"{snippet[:220].rstrip()}..."
            detail = f" - {snippet}" if snippet else ""
            lines.append(f"{index}. {source['title']}{detail}")
        return "\n".join(lines)

    def _search(self, question: str) -> list[dict[str, Any]]:
        errors: list[str] = []
        provider = self.settings.web_search_provider.strip().lower()

        if provider in {"ollama", "auto"}:
            try:
                return self._search_ollama(question)
            except Exception as exc:
                errors.append(f"ollama: {exc}")
                logger.warning("Ollama web search failed: %s", exc)
                if provider == "ollama":
                    raise RuntimeError("; ".join(errors)) from exc

        try:
            return self._search_duckduckgo(question)
        except Exception as exc:
            errors.append(f"duckduckgo: {exc}")
            raise RuntimeError("; ".join(errors)) from exc

    def _search_ollama(self, question: str) -> list[dict[str, Any]]:
        if not self.settings.ollama_api_key:
            raise RuntimeError("OLLAMA_API_KEY is required for Ollama web search")

        import httpx

        base_url = self.settings.ollama_base_url.rstrip("/")
        if base_url.endswith("/api"):
            url = f"{base_url}/web_search"
        else:
            url = f"{base_url}/api/web_search"

        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.settings.ollama_api_key}"},
            json={"query": question, "max_results": min(self.settings.top_k, 10)},
            timeout=30.0,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"{exc.response.status_code} {exc.response.text.strip()}") from exc

        data = response.json()
        results = data.get("results", [])
        return [
            {
                "title": item.get("title"),
                "href": item.get("url"),
                "body": item.get("content"),
            }
            for item in results
            if item.get("url")
        ]

    def _search_duckduckgo(self, question: str) -> list[dict[str, Any]]:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        errors: list[str] = []
        with DDGS() as ddgs:
            for backend in ("auto", "lite", "html"):
                try:
                    results = list(ddgs.text(question, backend=backend, max_results=5))
                    if results:
                        return results
                    errors.append(f"{backend}: no results")
                except Exception as exc:
                    errors.append(f"{backend}: {exc}")
                    logger.warning("DuckDuckGo backend %s failed: %s", backend, exc)

        raise RuntimeError("; ".join(errors) or "No DuckDuckGo results returned")

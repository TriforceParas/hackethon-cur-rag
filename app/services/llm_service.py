import json
from typing import Any

import httpx

from app.core.config import Settings, get_settings


class LLMService:
    """Provider abstraction for text generation through Ollama or Groq."""

    def __init__(self, settings: Settings | None = None, timeout: float = 60.0) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        provider = self.settings.normalized_provider
        if provider == "groq":
            return self._generate_groq(prompt, system_prompt)
        return self._generate_ollama(prompt, system_prompt)

    def _generate_ollama(self, prompt: str, system_prompt: str | None) -> str:
        errors: list[str] = []
        for think in self._ollama_think_attempts():
            try:
                return self._generate_ollama_chat(prompt, system_prompt, think)
            except Exception as exc:
                errors.append(f"chat[{think}]: {exc}")

        try:
            return self._generate_ollama_completion(prompt, system_prompt)
        except Exception as exc:
            errors.append(f"generate: {exc}")
            raise RuntimeError(f"Ollama generation failed. {'; '.join(errors)}") from exc

    def _generate_ollama_chat(self, prompt: str, system_prompt: str | None, think: str | bool) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append(
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Always write a visible final answer in message.content.",
                }
            )
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "stream": False,
            "think": think,
            "options": {"temperature": 0.2, "num_predict": 4096},
        }
        data = self._post_ollama("/chat", payload)
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError(f"Ollama chat returned an empty response. {self._describe_ollama_response(data)}")
        return content

    def _generate_ollama_completion(self, prompt: str, system_prompt: str | None) -> str:
        payload: dict[str, Any] = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "think": self._ollama_think_value(),
            "options": {"temperature": 0.2, "num_predict": 4096},
        }
        if system_prompt:
            payload["system"] = system_prompt
        data = self._post_ollama("/generate", payload)
        content = data.get("response", "").strip()
        if not content:
            raise RuntimeError(f"Ollama generate returned an empty response. {self._describe_ollama_response(data)}")
        return content

    @staticmethod
    def _describe_ollama_response(data: dict[str, Any]) -> str:
        message = data.get("message") or {}
        message_keys = list(message.keys()) if isinstance(message, dict) else []
        has_thinking = bool(message.get("thinking")) if isinstance(message, dict) else bool(data.get("thinking"))
        return (
            f"model={data.get('model')!r}, done_reason={data.get('done_reason')!r}, "
            f"eval_count={data.get('eval_count')!r}, prompt_eval_count={data.get('prompt_eval_count')!r}, "
            f"has_thinking={has_thinking!r}, response_keys={list(data.keys())}, message_keys={message_keys}"
        )

    def _ollama_think_value(self) -> str | bool:
        value = str(self.settings.ollama_think).strip().lower()
        if self.settings.ollama_model.startswith("gpt-oss") and value in {"false", "off", "no", "none", "0", ""}:
            return "low"
        if value in {"false", "off", "no", "none", "0", ""}:
            return False
        if value in {"true", "on", "yes", "1"}:
            return True
        return value

    def _ollama_think_attempts(self) -> list[str | bool]:
        primary = self._ollama_think_value()
        if not self.settings.ollama_model.startswith("gpt-oss"):
            return [primary]

        attempts: list[str | bool] = []
        for value in [primary, "medium", "high"]:
            if value not in attempts:
                attempts.append(value)
        return attempts

    def _post_ollama(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        if self.settings.ollama_api_key:
            headers["Authorization"] = f"Bearer {self.settings.ollama_api_key}"

        try:
            response = httpx.post(
                self._ollama_api_url(path),
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            raise RuntimeError(f"Ollama generation failed: {exc.response.status_code} {detail}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Ollama generation failed: {exc}") from exc

        return response.json()

    def _ollama_api_url(self, path: str) -> str:
        base_url = self.settings.ollama_base_url.rstrip("/")
        if base_url.endswith("/api"):
            return f"{base_url}{path}"
        return f"{base_url}/api{path}"

    def _generate_groq(self, prompt: str, system_prompt: str | None) -> str:
        if not self.settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required when LLM_PROVIDER=groq")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.groq_api_key}"},
                json={"model": self.settings.groq_model, "messages": messages, "temperature": 0.2},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            raise RuntimeError(f"Groq generation failed: {exc.response.status_code} {detail}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Groq generation failed: {exc}") from exc

        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    @staticmethod
    def parse_json_response(text: str) -> dict[str, Any] | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
        return None

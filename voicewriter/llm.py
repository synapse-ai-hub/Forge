"""Minimal LLM clients: OpenAI-compatible and Ollama (stdlib HTTP only)."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from voicewriter import config


class LlmError(RuntimeError):
    """Raised when an LLM backend fails or is not configured."""


class LlmClient:
    def __init__(
        self,
        provider: str,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        temperature: float = 0.7,
        timeout: float = 120.0,
    ) -> None:
        self.provider = provider
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.model and self.provider)

    def complete(self, system: str, user: str) -> str:
        if not self.configured:
            raise LlmError(
                "No LLM backend configured. Set VOICEWRITER_LLM_PROVIDER, "
                "VOICEWRITER_LLM_BASE_URL and VOICEWRITER_LLM_MODEL."
            )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if self.provider == "ollama":
            return self._complete_ollama(messages)
        return self._complete_openai_compatible(messages)

    async def complete_async(self, system: str, user: str) -> str:
        return await asyncio.to_thread(self.complete, system, user)

    def _post_json(self, url: str, payload: dict, headers: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise LlmError(f"HTTP {exc.code} from {url}: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LlmError(f"Request failed for {url}: {exc}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise LlmError(f"Invalid JSON from {url}: {body[:200]}") from exc

    def _complete_openai_compatible(self, messages: list[dict]) -> str:
        base = self.base_url.rstrip("/") or "https://api.openai.com/v1"
        url = f"{base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        data = self._post_json(url, payload, headers)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError(f"Unexpected OpenAI-compatible response: {data}") from exc

    def _complete_ollama(self, messages: list[dict]) -> str:
        base = self.base_url.rstrip("/") or "http://localhost:11434"
        url = f"{base}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        data = self._post_json(url, payload, {"Content-Type": "application/json"})
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LlmError(f"Unexpected Ollama response: {data}") from exc


def from_config(cfg: config.LlmConfig | None = None) -> LlmClient:
    cfg = cfg or config.load_llm_config()
    return LlmClient(
        provider=cfg.provider,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=cfg.model,
        temperature=cfg.temperature,
        timeout=cfg.timeout,
    )

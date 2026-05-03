"""0G Compute inference client — OpenAI-compatible API wrapping Qwen 2.5 7B on 0G testnet."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


# Default model available on 0G Compute testnet
_DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"


@dataclass
class ChatMessage:
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class InferenceConfig:
    """Configuration for 0G Compute inference."""
    service_url: str            # e.g. "https://<provider>.0g.ai"
    api_key: str                # "app-sk-<SECRET>" from 0g-compute-cli
    model: str = _DEFAULT_MODEL
    max_tokens: int = 2048
    temperature: float = 0.7
    timeout: int = 60


class ZeroGInferenceClient:
    """
    Chat inference via 0G Compute testnet (OpenAI-compatible proxy).

    Usage:
        client = ZeroGInferenceClient(
            service_url="https://<provider>.0g.ai",
            api_key="app-sk-<SECRET>",
        )
        reply = client.chat([ChatMessage("user", "Hello!")])

    Falls back to a plain OpenAI client (using OPENAI_API_KEY env var) if
    service_url is not configured — useful for local development.
    """

    def __init__(
        self,
        service_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        timeout: int = 60,
    ):
        self.service_url = (service_url or os.environ.get("ZEROG_SERVICE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("ZEROG_API_KEY", "")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            )

        if self.service_url and self.api_key:
            # 0G Compute testnet — proxy endpoint
            self._client = OpenAI(
                base_url=f"{self.service_url}/v1/proxy",
                api_key=self.api_key,
                timeout=self.timeout,
            )
        else:
            # Fallback: plain OpenAI (for local dev / testing)
            # Log a clear warning so operators know they're NOT on 0G Compute
            openai_key = os.environ.get("OPENAI_API_KEY", "")
            if not openai_key:
                raise RuntimeError(
                    "No 0G Compute credentials (ZEROG_SERVICE_URL + ZEROG_API_KEY) "
                    "or OPENAI_API_KEY configured."
                )
            logger.warning(
                "ZEROG_SERVICE_URL / ZEROG_API_KEY not configured — "
                "falling back to OpenAI (inference is NOT running on 0G Compute). "
                "Set ZEROG_SERVICE_URL and ZEROG_API_KEY to use 0G."
            )
            self._client = OpenAI(api_key=openai_key, timeout=self.timeout)

        return self._client

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        system: Optional[str] = None,
    ) -> str:
        """Single-turn chat. Returns the assistant reply as a string."""
        payload = self._build_payload(messages, system=system)
        client = self._get_client()

        response = client.chat.completions.create(
            model=self.model,
            messages=payload,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content or ""

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        system: Optional[str] = None,
    ) -> Iterator[str]:
        """Streaming chat — yields text chunks as they arrive."""
        payload = self._build_payload(messages, system=system)
        client = self._get_client()

        stream = client.chat.completions.create(
            model=self.model,
            messages=payload,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def _build_payload(
        self,
        messages: list[ChatMessage],
        *,
        system: Optional[str] = None,
    ) -> list[dict]:
        payload = []
        if system:
            payload.append({"role": "system", "content": system})
        for m in messages:
            payload.append({"role": m.role, "content": m.content})
        return payload

import urllib.request
import json
import logging
from typing import Optional

from ....application.ports.outbound.llm_port import LLMProviderPort

logger = logging.getLogger(__name__)


class OpenAICompatibleLLMAdapter(LLMProviderPort):
    """Adapter for querying any OpenAI-compatible LLM endpoint (Ollama, vLLM, LMStudio, OpenAI)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "ollama",
        model: str = "llama3",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error calling LLM endpoint {url}: {e}")
            raise RuntimeError(f"LLM generation failed: {e}")

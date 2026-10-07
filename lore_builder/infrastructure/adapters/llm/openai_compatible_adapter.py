import urllib.request
import urllib.error
import json
import logging
import os
from typing import Optional

from ....application.ports.outbound.llm_port import LLMProviderPort

logger = logging.getLogger(__name__)


def _load_env_file():
    """Lightweight .env loader without requiring external python-dotenv."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(current_dir, "../../../.."))
    env_path = os.path.join(root_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key not in os.environ:
                        os.environ[key] = val


_load_env_file()


class OpenAICompatibleLLMAdapter(LLMProviderPort):
    """Adapter for querying any OpenAI-compatible LLM endpoint (OpenRouter, Ollama, vLLM, OpenAI)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("OPENROUTER_BASE_URL")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or "ollama"
        )
        self.model = (
            model
            or os.environ.get("OPENROUTER_MODEL")
            or "nvidia/nemotron-3-ultra-550b-a55b:free"
        )

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

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/bivex/lore_ai_builder",
            "X-Title": "Lore AI Builder",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"HTTP {e.code} error from LLM endpoint {url}: {err_body}")
            raise RuntimeError(f"LLM API HTTP {e.code} failed: {err_body}")
        except Exception as e:
            logger.error(f"Error calling LLM endpoint {url}: {e}")
            raise RuntimeError(f"LLM generation failed: {e}")

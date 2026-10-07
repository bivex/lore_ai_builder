import urllib.request
import urllib.error
import json
import logging
import os
from typing import Optional

from ....application.ports.outbound.llm_port import LLMProviderPort

logger = logging.getLogger(__name__)


def _load_env_file():
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
    """Strict adapter for querying OpenAI-compatible LLM endpoints (OpenRouter, etc.) with zero fallbacks."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        resolved_base_url = (
            base_url
            or os.environ.get("OPENROUTER_BASE_URL")
        )
        if not resolved_base_url:
            raise ValueError("LLM base_url is strictly required (set OPENROUTER_BASE_URL or pass base_url).")
        self.base_url = resolved_base_url.rstrip("/")

        resolved_api_key = (
            api_key
            or os.environ.get("OPENROUTER_API_KEY")
        )
        if not resolved_api_key:
            raise ValueError("LLM api_key is strictly required (set OPENROUTER_API_KEY or pass api_key).")
        self.api_key = resolved_api_key

        resolved_model = (
            model
            or os.environ.get("OPENROUTER_MODEL")
        )
        if not resolved_model:
            raise ValueError("LLM model is strictly required (set OPENROUTER_MODEL or pass model).")
        self.model = resolved_model

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
                choices = data.get("choices")
                if not choices or not isinstance(choices, list) or len(choices) == 0:
                    raise RuntimeError(f"LLM API returned invalid choices response: {data}")
                content = choices[0].get("message", {}).get("content")
                if content is None:
                    raise RuntimeError(f"LLM API message content is empty: {data}")
                return content
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"HTTP {e.code} error from LLM endpoint {url}: {err_body}")
            raise RuntimeError(f"LLM API HTTP {e.code} error: {err_body}")
        except Exception as e:
            logger.error(f"Error calling LLM endpoint {url}: {e}")
            raise RuntimeError(f"LLM invocation failed: {e}")

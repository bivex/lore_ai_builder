from abc import ABC, abstractmethod
from typing import Optional


class LLMProviderPort(ABC):
    """Outbound SPI port for generating text via Large Language Models."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> str:
        """Call LLM with specified prompt and return generated text."""
        pass

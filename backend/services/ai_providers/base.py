"""Abstract base class for all AI providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AIResponse:
    """Standardized response from any AI provider."""

    content: str
    input_tokens: int
    output_tokens: int
    model: str
    finish_reason: str = ""
    raw_response: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BaseAIProvider(ABC):
    """Base class that every AI provider must implement."""

    provider_type: str = ""

    @abstractmethod
    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        max_output_tokens: int = 8192,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> AIResponse:
        """Send code for security analysis and return the AI response.

        Args:
            system_prompt: The system-level instruction (role, format, etc.).
            user_prompt: The user-level content (code + context).
            model_id: Provider-specific model identifier.
            max_output_tokens: Maximum tokens the model may generate.
            api_key: API key (overrides any default).
            base_url: Custom API endpoint (overrides any default).

        Returns:
            AIResponse with content, token counts, and metadata.
        """
        pass

    @abstractmethod
    async def test_connection(
        self,
        api_key: str,
        model_id: str,
        base_url: str | None = None,
    ) -> bool:
        """Test whether the provider is reachable with the given credentials.

        Args:
            api_key: API key to validate.
            model_id: Model to test against.
            base_url: Optional custom endpoint.

        Returns:
            True if the connection succeeds, False otherwise.
        """
        pass

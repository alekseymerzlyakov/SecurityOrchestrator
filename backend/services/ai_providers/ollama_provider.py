"""Ollama local AI provider using httpx for HTTP communication."""

import logging

import httpx

from backend.services.ai_providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
OLLAMA_TIMEOUT = 600.0  # 10 minutes for large model responses


class OllamaProvider(BaseAIProvider):
    """Provider implementation for locally-running Ollama models."""

    provider_type = "ollama"

    def _get_base_url(self, base_url: str | None = None) -> str:
        """Resolve the Ollama server base URL."""
        return (base_url or DEFAULT_OLLAMA_URL).rstrip("/")

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        max_output_tokens: int = 8192,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> AIResponse:
        """Analyze code using a locally-running Ollama model."""
        url = self._get_base_url(base_url)

        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "num_predict": max_output_tokens,
                "temperature": 0.1,
            },
        }

        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            try:
                response = await client.post(f"{url}/api/chat", json=payload)
                response.raise_for_status()
            except httpx.ConnectError as exc:
                logger.error("Cannot connect to Ollama at %s: %s", url, exc)
                raise ConnectionError(
                    f"Cannot connect to Ollama server at {url}. "
                    "Make sure Ollama is running."
                ) from exc
            except httpx.HTTPStatusError as exc:
                logger.error("Ollama HTTP error %s: %s", exc.response.status_code, exc)
                raise RuntimeError(
                    f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}"
                ) from exc

        data = response.json()

        # Extract content from Ollama response
        message = data.get("message", {})
        content = message.get("content", "")

        # Token counts
        input_tokens = data.get("prompt_eval_count", 0) or 0
        output_tokens = data.get("eval_count", 0) or 0

        # Finish reason
        finish_reason = "stop" if data.get("done", False) else "length"
        done_reason = data.get("done_reason", "")
        if done_reason:
            finish_reason = done_reason

        return AIResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=data.get("model", model_id),
            finish_reason=finish_reason,
            raw_response={
                "total_duration": data.get("total_duration"),
                "load_duration": data.get("load_duration"),
                "eval_duration": data.get("eval_duration"),
            },
        )

    async def test_connection(
        self,
        api_key: str,
        model_id: str,
        base_url: str | None = None,
    ) -> bool:
        """Test connection by fetching the list of available models."""
        url = self._get_base_url(base_url)

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(f"{url}/api/tags")
                response.raise_for_status()
                data = response.json()

                # Verify the requested model is available
                models = data.get("models", [])
                available_names = [m.get("name", "") for m in models]

                if model_id in available_names or any(
                    model_id in name for name in available_names
                ):
                    return True

                # Model not found but server is reachable
                logger.warning(
                    "Ollama server reachable but model '%s' not found. "
                    "Available: %s",
                    model_id,
                    available_names,
                )
                return True  # Server is up; model may be pulled on demand

            except Exception as exc:
                logger.warning("Ollama connection test failed: %s", exc)
                return False

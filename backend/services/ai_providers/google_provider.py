"""Google Generative AI provider using the google-generativeai SDK."""

import logging

import google.generativeai as genai

from backend.services.ai_providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)


class GoogleProvider(BaseAIProvider):
    """Provider implementation for Google Gemini models."""

    provider_type = "google"

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        max_output_tokens: int = 8192,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> AIResponse:
        """Analyze code using a Google Gemini model.

        Note: google-generativeai is synchronous under the hood for
        generate_content, so we call it directly. For true async you
        would wrap in asyncio.to_thread, but the library handles I/O
        internally.
        """
        if api_key:
            genai.configure(api_key=api_key)

        generation_config = genai.types.GenerationConfig(
            max_output_tokens=max_output_tokens,
            temperature=0.1,
        )

        model = genai.GenerativeModel(
            model_name=model_id,
            system_instruction=system_prompt,
            generation_config=generation_config,
        )

        try:
            response = model.generate_content(user_prompt)

            content = response.text or ""

            # Extract token counts from usage metadata
            usage = getattr(response, "usage_metadata", None)
            input_tokens = 0
            output_tokens = 0
            if usage:
                input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                output_tokens = getattr(usage, "candidates_token_count", 0) or 0

            # Determine finish reason
            finish_reason = ""
            if response.candidates:
                candidate = response.candidates[0]
                fr = getattr(candidate, "finish_reason", None)
                if fr is not None:
                    finish_reason = str(fr.name) if hasattr(fr, "name") else str(fr)

            return AIResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_id,
                finish_reason=finish_reason,
                raw_response={
                    "prompt_feedback": str(getattr(response, "prompt_feedback", "")),
                },
            )
        except Exception as exc:
            logger.error("Google AI error: %s", exc)
            raise RuntimeError(f"Google Generative AI error: {exc}") from exc

    async def test_connection(
        self,
        api_key: str,
        model_id: str,
        base_url: str | None = None,
    ) -> bool:
        """Test connection by listing models or sending a simple generate."""
        try:
            genai.configure(api_key=api_key)

            model = genai.GenerativeModel(model_name=model_id)
            response = model.generate_content("Reply with OK.")

            return bool(response.text)
        except Exception as exc:
            logger.warning("Google AI connection test failed: %s", exc)
            return False

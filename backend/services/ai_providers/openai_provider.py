"""OpenAI AI provider using the official openai SDK."""

import logging

import openai

from backend.services.ai_providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseAIProvider):
    """Provider implementation for OpenAI models (GPT-4o, GPT-4-turbo, etc.)."""

    provider_type = "openai"

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        max_output_tokens: int = 8192,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> AIResponse:
        """Analyze code using an OpenAI model."""
        client_kwargs: dict = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url

        client = openai.AsyncOpenAI(**client_kwargs)

        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_output_tokens,
                temperature=0.1,
            )

            choice = response.choices[0]
            content = choice.message.content or ""

            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

            return AIResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=response.model or model_id,
                finish_reason=choice.finish_reason or "",
                raw_response={
                    "id": response.id,
                    "object": response.object,
                    "finish_reason": choice.finish_reason,
                },
            )
        except openai.APIConnectionError as exc:
            logger.error("OpenAI connection error: %s", exc)
            raise ConnectionError(f"Failed to connect to OpenAI API: {exc}") from exc
        except openai.RateLimitError as exc:
            logger.error("OpenAI rate limit exceeded: %s", exc)
            raise RuntimeError(f"OpenAI rate limit exceeded: {exc}") from exc
        except openai.APIStatusError as exc:
            logger.error("OpenAI API error %s: %s", exc.status_code, exc.message)
            raise RuntimeError(
                f"OpenAI API error (status {exc.status_code}): {exc.message}"
            ) from exc
        finally:
            await client.close()

    async def test_connection(
        self,
        api_key: str,
        model_id: str,
        base_url: str | None = None,
    ) -> bool:
        """Test connection by sending a minimal completion request."""
        client_kwargs: dict = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = openai.AsyncOpenAI(**client_kwargs)

        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Reply with OK."}],
                max_tokens=16,
            )
            return len(response.choices) > 0
        except Exception as exc:
            logger.warning("OpenAI connection test failed: %s", exc)
            return False
        finally:
            await client.close()

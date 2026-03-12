"""Anthropic (Claude) AI provider using the official anthropic SDK."""

import asyncio
import logging

import anthropic

from backend.services.ai_providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)

# Retry settings for rate limit / overload errors
_MAX_RETRIES = 4
_RETRY_DELAYS = [5, 15, 30, 60]  # seconds between attempts


class AnthropicProvider(BaseAIProvider):
    """Provider implementation for Anthropic Claude models."""

    provider_type = "anthropic"

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        max_output_tokens: int = 8192,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> AIResponse:
        """Analyze code using an Anthropic Claude model."""
        client_kwargs: dict = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        # Sanity check: base_url must look like a URL, not an API key
        if base_url and base_url.strip().startswith("http"):
            client_kwargs["base_url"] = base_url.strip()
        elif base_url:
            logger.warning("Ignoring base_url that does not start with http: %r", base_url[:20])

        client = anthropic.AsyncAnthropic(**client_kwargs)

        try:
            response = await self._call_with_retry(
                client, model_id, system_prompt, user_prompt, max_output_tokens
            )

            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            return AIResponse(
                content=content,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                model=response.model,
                finish_reason=response.stop_reason or "",
                raw_response={
                    "id": response.id,
                    "type": response.type,
                    "stop_reason": response.stop_reason,
                },
            )
        except anthropic.APIConnectionError as exc:
            # On some systems APIConnectionError wraps a real HTTP error — check cause
            cause = exc.__cause__
            cause_str = str(cause) if cause else ""
            exc_str = str(exc)
            logger.error("Anthropic connection error cause=%r exc=%r", cause_str, exc_str)
            # If the real cause is a credit/billing error disguised as connection error
            combined = (cause_str + exc_str).lower()
            if "credit balance" in combined or "too low" in combined or "billing" in combined:
                raise RuntimeError(f"Anthropic API error (status 400): {exc}") from exc
            raise ConnectionError(f"Failed to connect to Anthropic API: {exc}") from exc
        except anthropic.RateLimitError as exc:
            logger.error("Anthropic rate limit exceeded after all retries: %s", exc)
            raise RuntimeError(f"Anthropic rate limit exceeded: {exc}") from exc
        except anthropic.APIStatusError as exc:
            logger.error("Anthropic API error %s: %s", exc.status_code, exc.message)
            raise RuntimeError(
                f"Anthropic API error (status {exc.status_code}): {exc.message}"
            ) from exc
        finally:
            await client.close()

    async def _call_with_retry(
        self,
        client: anthropic.AsyncAnthropic,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
    ):
        """Call client.messages.create() with retry on rate limit / overload.

        Retries up to _MAX_RETRIES times with increasing delays.
        Raises the original exception if all retries are exhausted.
        """
        last_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await client.messages.create(
                    model=model_id,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    max_tokens=max_output_tokens,
                )
            except anthropic.RateLimitError as exc:
                last_exc = exc
                if attempt == _MAX_RETRIES - 1:
                    break
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "Rate limit hit (attempt %d/%d), retrying in %ds...",
                    attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
            except anthropic.APIStatusError as exc:
                # 529 = Anthropic API overloaded
                if exc.status_code == 529:
                    last_exc = exc
                    if attempt == _MAX_RETRIES - 1:
                        break
                    delay = _RETRY_DELAYS[attempt]
                    logger.warning(
                        "API overloaded 529 (attempt %d/%d), retrying in %ds...",
                        attempt + 1, _MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise  # non-retryable status error — re-raise immediately

        # All retries exhausted
        raise last_exc

    async def test_connection(
        self,
        api_key: str,
        model_id: str,
        base_url: str | None = None,
    ) -> bool:
        """Test connection by sending a minimal message."""
        client_kwargs: dict = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = anthropic.AsyncAnthropic(**client_kwargs)

        try:
            response = await client.messages.create(
                model=model_id,
                messages=[{"role": "user", "content": "Reply with OK."}],
                max_tokens=16,
            )
            return len(response.content) > 0
        except Exception as exc:
            logger.warning("Anthropic connection test failed: %s", exc)
            return False
        finally:
            await client.close()

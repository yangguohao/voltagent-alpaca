"""Groq API client with per-model rate limiting and resilient JSON parsing."""

import asyncio
import time
from typing import Type, TypeVar

from groq import Groq
from pydantic import BaseModel

from ai_agent.config.settings import Settings
from ai_agent.core.state import StateStore
from ai_agent.llm.cache import ResponseCache
from ai_agent.llm.json_utils import parse_model_response
from ai_agent.observability.logger import get_logger

logger = get_logger("groq_client")
T = TypeVar("T", bound=BaseModel)


class RateLimiter:
    def __init__(self, rpm: int, rpd: int, tpd: int) -> None:
        self.rpm = rpm
        self.rpd = rpd
        self.tpd = tpd
        self._minute_requests: list[float] = []
        self._day_requests: list[tuple[float, int]] = []
        self._day_tokens = 0
        self._day_start = time.time()

    def _reset_day_if_needed(self) -> None:
        if time.time() - self._day_start > 86400:
            self._day_requests.clear()
            self._day_tokens = 0
            self._day_start = time.time()

    def acquire(self, estimated_tokens: int = 500) -> None:
        self._reset_day_if_needed()
        now = time.time()
        self._minute_requests = [t for t in self._minute_requests if now - t < 60]
        self._day_requests = [(t, tok) for t, tok in self._day_requests if now - t < 86400]
        self._day_tokens = sum(tok for _, tok in self._day_requests)

        if len(self._minute_requests) >= self.rpm:
            sleep_time = 60 - (now - self._minute_requests[0]) + 0.1
            logger.warning("RPM limit hit, sleeping %.1fs", sleep_time)
            time.sleep(max(0, sleep_time))
        if len(self._day_requests) >= self.rpd:
            raise RuntimeError("Daily request limit reached for model")
        if self._day_tokens + estimated_tokens > self.tpd:
            raise RuntimeError("Daily token limit reached for model")

        self._minute_requests.append(time.time())
        self._day_requests.append((time.time(), estimated_tokens))

    async def acquire_async(self, estimated_tokens: int = 500) -> None:
        await asyncio.to_thread(self.acquire, estimated_tokens)


class GroqClient:
    def __init__(self, settings: Settings, state: StateStore | None = None) -> None:
        self.settings = settings
        self.state = state
        self.client = Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None
        self.cache = ResponseCache()
        self.limiters = {
            settings.groq_model_fast: RateLimiter(rpm=25, rpd=900, tpd=1_800_000),
            settings.groq_model_smart: RateLimiter(rpm=25, rpd=900, tpd=180_000),
        }

    def _call_api(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        json_mode: bool,
    ):
        kwargs: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return self.client.chat.completions.create(**kwargs)

    async def complete(
        self,
        model: str,
        messages: list[dict],
        schema: Type[T],
        task: str = "unknown",
        max_tokens: int | None = None,
        max_retries: int = 3,
        fallback_model: str | None = None,
        use_cache: bool = True,
    ) -> T:
        if self.client is None:
            raise RuntimeError("GROQ_API_KEY not configured")

        schema_name = schema.__name__
        if use_cache:
            cached = self.cache.get(model, messages, schema_name)
            if cached is not None:
                return cached

        tokens = max_tokens or self.settings.gpt_oss_max_tokens
        attempts: list[tuple[str, bool]] = [(model, False), (model, True)]
        if fallback_model and fallback_model != model:
            attempts.extend([(fallback_model, True), (fallback_model, False)])

        last_error: Exception | None = None

        for attempt_model, json_mode in attempts:
            limiter = self.limiters.get(attempt_model)
            if limiter is None:
                continue

            for attempt in range(max_retries):
                try:
                    await limiter.acquire_async(estimated_tokens=tokens + 300)
                    response = await asyncio.to_thread(
                        self._call_api, attempt_model, messages, tokens, json_mode,
                    )
                    content = response.choices[0].message.content or "{}"
                    result = parse_model_response(content, schema)

                    if use_cache:
                        self.cache.set(model, messages, schema_name, result)

                    if self.state:
                        usage = response.usage
                        self.state.log_llm(
                            task=task,
                            model=attempt_model,
                            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                            response=content,
                        )

                    if attempt_model != model or not json_mode:
                        logger.info(
                            "LLM %s succeeded via model=%s json_mode=%s",
                            task, attempt_model, json_mode,
                        )
                    return result

                except Exception as exc:
                    last_error = exc
                    err = str(exc)
                    retryable = (
                        "429" in err
                        or "json_validate_failed" in err
                        or "Failed to generate JSON" in err
                        or "Failed to validate JSON" in err
                        or isinstance(exc, ValueError)
                    )
                    if retryable and attempt < max_retries - 1:
                        wait = 2 ** attempt
                        logger.warning(
                            "LLM %s retry %d model=%s json=%s: %s",
                            task, attempt + 1, attempt_model, json_mode, exc,
                        )
                        await asyncio.sleep(wait)
                        continue
                    logger.warning(
                        "LLM %s failed model=%s json=%s: %s",
                        task, attempt_model, json_mode, exc,
                    )
                    break

        raise RuntimeError(f"Groq request failed for {task}") from last_error

"""LLM client wrapper with retry logic, rate limiting, and structured JSON output parsing.

Uses the OpenAI-compatible chat completions API so it works with any provider:
Anthropic, Nous Research Portal, OpenRouter, local vLLM, etc.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, APIError, RateLimitError

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    raw_response: Any = None


class LLMClient:
    """Async wrapper around any OpenAI-compatible API with retry logic and rate limiting."""

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        max_concurrent: int = 20,
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
    ):
        resolved_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        resolved_base = api_base or os.environ.get("LLM_API_BASE")

        kwargs: dict[str, Any] = {"api_key": resolved_key}
        if resolved_base:
            kwargs["base_url"] = resolved_base

        self._client = AsyncOpenAI(**kwargs)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_retries = max_retries
        self._base_retry_delay = base_retry_delay
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def reset_call_count(self) -> None:
        self._call_count = 0

    async def call(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        async with self._semaphore:
            return await self._call_with_retry(model, system, user, max_tokens, temperature)

    async def _call_with_retry(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        last_error: Exception | None = None
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        for attempt in range(self._max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                self._call_count += 1
                choice = response.choices[0] if response.choices else None
                content = choice.message.content if choice and choice.message else ""
                usage = response.usage
                return LLMResponse(
                    content=content or "",
                    model=response.model or model,
                    input_tokens=usage.prompt_tokens if usage else 0,
                    output_tokens=usage.completion_tokens if usage else 0,
                    raw_response=response,
                )
            except RateLimitError as e:
                last_error = e
                delay = self._base_retry_delay * (2 ** attempt)
                logger.warning("Rate limited (attempt %d/%d), retrying in %.1fs", attempt + 1, self._max_retries, delay)
                await asyncio.sleep(delay)
            except APIError as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._base_retry_delay * (2 ** attempt)
                    logger.warning("API error (attempt %d/%d): %s, retrying in %.1fs", attempt + 1, self._max_retries, e, delay)
                    await asyncio.sleep(delay)
                else:
                    raise
            except Exception as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._base_retry_delay * (2 ** attempt)
                    logger.warning("Unexpected error (attempt %d/%d): %s, retrying in %.1fs", attempt + 1, self._max_retries, e, delay)
                    await asyncio.sleep(delay)
                else:
                    raise
        raise last_error  # type: ignore[misc]

    async def call_json(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> dict:
        """Call the LLM and parse the response as JSON. Retries with clarification on parse failure."""
        response = await self.call(model, system, user, max_tokens, temperature)
        parsed = _try_parse_json(response.content)
        if parsed is not None:
            return parsed

        retry_prompt = (
            f"Your previous response was not valid JSON. Please respond with ONLY a valid JSON object, "
            f"no markdown fences, no explanation.\n\nOriginal request:\n{user}"
        )
        response = await self.call(model, system, retry_prompt, max_tokens, temperature)
        parsed = _try_parse_json(response.content)
        if parsed is not None:
            return parsed

        raise ValueError(f"Failed to get valid JSON from LLM after retry. Last response: {response.content[:500]}")

    async def call_code(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        """Call the LLM and extract Python code from the response."""
        response = await self.call(model, system, user, max_tokens, temperature)
        code = _extract_python_code(response.content)
        if code:
            return code

        retry_prompt = (
            f"Your previous response did not contain valid Python code. "
            f"Please respond with ONLY the Python code, no markdown fences, no explanation.\n\n"
            f"Original request:\n{user}"
        )
        response = await self.call(model, system, retry_prompt, max_tokens, temperature)
        code = _extract_python_code(response.content)
        if code:
            return code

        raise ValueError(f"Failed to get valid Python code from LLM after retry. Last response: {response.content[:500]}")


def _try_parse_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _extract_python_code(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:python)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if "class AttackStrategy" in text:
        lines = text.split("\n")
        code_lines = []
        in_code = False
        for line in lines:
            if line.strip().startswith("class ") or in_code:
                in_code = True
                code_lines.append(line)
            elif line.strip().startswith("import ") or line.strip().startswith("from "):
                code_lines.append(line)
        if code_lines:
            return "\n".join(code_lines)
    return text if text else ""


_default_client: LLMClient | None = None


def get_llm_client(
    max_concurrent: int = 20,
    api_base: str | None = None,
    api_key: str | None = None,
) -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient(
            api_base=api_base,
            api_key=api_key,
            max_concurrent=max_concurrent,
        )
    return _default_client


def set_llm_client(client: LLMClient) -> None:
    global _default_client
    _default_client = client

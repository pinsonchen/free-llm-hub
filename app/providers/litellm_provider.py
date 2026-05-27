"""LiteLLM-based provider call wrapper with usage/ratelimit extraction."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import litellm

from app.core.router import Candidate

litellm.drop_params = True


@dataclass
class ProviderResponse:
    data: Any
    total_tokens: int
    remaining_requests: int | None = None
    remaining_tokens: int | None = None
    reset_requests_seconds: float | None = None
    reset_tokens_seconds: float | None = None


def _build_litellm_model_name(candidate: Candidate) -> str:
    provider = candidate.provider
    model = candidate.model

    if provider == "groq":
        return f"groq/{model}"
    elif provider == "gemini":
        return f"gemini/{model}"
    elif provider == "cerebras":
        return f"cerebras/{model}"
    elif provider in (
        "siliconflow",
        "zhipu",
        "deepseek",
        "openrouter",
        "kimi",
        "cloudflare",
    ):
        return f"openai/{model}"
    else:
        return f"openai/{model}"


def _build_litellm_kwargs(candidate: Candidate) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"api_key": candidate.key}
    provider = candidate.provider

    # Gemini uses query-style auth via key only; no api_base.
    if provider == "gemini":
        return kwargs

    kwargs["api_base"] = candidate.endpoint
    return kwargs


def _extract_usage(response: Any) -> int:
    """Extract total_tokens from LiteLLM response."""
    try:
        if hasattr(response, "usage") and response.usage:
            return response.usage.total_tokens or 0
    except Exception:
        pass
    return 0


def _extract_ratelimit_headers(response: Any) -> dict[str, Any]:
    """Extract x-ratelimit-* info from LiteLLM response headers."""
    info: dict[str, Any] = {}
    try:
        headers = None
        if hasattr(response, "_hidden_params"):
            headers = getattr(response._hidden_params, "additional_headers", None)
        if not headers and hasattr(response, "_response_headers"):
            headers = response._response_headers

        if not headers:
            return info

        if isinstance(headers, dict):
            h = {k.lower(): v for k, v in headers.items()}
        else:
            return info

        if "x-ratelimit-remaining-requests" in h:
            info["remaining_requests"] = int(h["x-ratelimit-remaining-requests"])
        if "x-ratelimit-remaining-tokens" in h:
            info["remaining_tokens"] = int(h["x-ratelimit-remaining-tokens"])
        if "x-ratelimit-reset-requests" in h:
            info["reset_requests_seconds"] = _parse_reset(h["x-ratelimit-reset-requests"])
        if "x-ratelimit-reset-tokens" in h:
            info["reset_tokens_seconds"] = _parse_reset(h["x-ratelimit-reset-tokens"])
    except Exception:
        pass
    return info


def _parse_reset(value: str) -> float:
    """Parse reset time like '1s', '60s', '1m30s', '2m' into seconds."""
    value = value.strip()
    if value.endswith("ms"):
        return float(value[:-2]) / 1000
    total = 0.0
    current = ""
    for ch in value:
        if ch.isdigit() or ch == ".":
            current += ch
        elif ch == "m":
            total += float(current) * 60 if current else 0
            current = ""
        elif ch == "s":
            total += float(current) if current else 0
            current = ""
        elif ch == "h":
            total += float(current) * 3600 if current else 0
            current = ""
    if current:
        total += float(current)
    return total


async def call_provider(
    candidate: Candidate,
    messages: list[dict[str, Any]],
    stream: bool = False,
    **extra: Any,
) -> ProviderResponse:
    model_name = _build_litellm_model_name(candidate)
    kwargs = _build_litellm_kwargs(candidate)

    response = await litellm.acompletion(
        model=model_name,
        messages=messages,
        stream=stream,
        **kwargs,
        **extra,
    )

    total_tokens = _extract_usage(response)
    rl_info = _extract_ratelimit_headers(response)

    return ProviderResponse(
        data=response,
        total_tokens=total_tokens,
        **rl_info,
    )


async def call_provider_streaming(
    candidate: Candidate,
    messages: list[dict[str, Any]],
    **extra: Any,
) -> AsyncIterator[Any]:
    model_name = _build_litellm_model_name(candidate)
    kwargs = _build_litellm_kwargs(candidate)

    response = await litellm.acompletion(
        model=model_name,
        messages=messages,
        stream=True,
        **kwargs,
        **extra,
    )
    return response

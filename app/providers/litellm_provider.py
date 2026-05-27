"""LiteLLM-based provider call wrapper."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import litellm

from app.core.router import Candidate

litellm.drop_params = True


def _build_litellm_model_name(candidate: Candidate) -> str:
    provider = candidate.provider
    model = candidate.model

    if provider == "groq":
        return f"groq/{model}"
    elif provider == "gemini":
        return f"gemini/{model}"
    elif provider in ("siliconflow", "zhipu", "deepseek", "openrouter"):
        return f"openai/{model}"
    else:
        return f"openai/{model}"


def _build_litellm_kwargs(candidate: Candidate) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    provider = candidate.provider

    if provider == "groq":
        kwargs["api_key"] = candidate.key
        kwargs["api_base"] = candidate.endpoint
    elif provider == "gemini":
        kwargs["api_key"] = candidate.key
    elif provider in ("siliconflow", "zhipu", "deepseek", "openrouter"):
        kwargs["api_key"] = candidate.key
        kwargs["api_base"] = candidate.endpoint
    else:
        kwargs["api_key"] = candidate.key
        kwargs["api_base"] = candidate.endpoint

    return kwargs


async def call_provider(
    candidate: Candidate,
    messages: list[dict[str, Any]],
    stream: bool = False,
    **extra: Any,
) -> Any:
    model_name = _build_litellm_model_name(candidate)
    kwargs = _build_litellm_kwargs(candidate)

    response = await litellm.acompletion(
        model=model_name,
        messages=messages,
        stream=stream,
        **kwargs,
        **extra,
    )
    return response


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

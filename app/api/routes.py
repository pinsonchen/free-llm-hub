"""OpenAI-compatible /v1/chat/completions and /v1/models API routes."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import get_config
from app.core.logger import log_decision
from app.core.registry import get_registry
from app.core.router import Candidate, resolve_candidates, resolve_for_physical_model
from app.core.scheduler import scheduler
from app.providers.litellm_provider import call_provider, call_provider_streaming

router = APIRouter()

MAX_RETRIES = 3


class ChatMessage(BaseModel):
    role: str
    content: str | list | None = None
    name: str | None = None
    tool_calls: list | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "auto"
    messages: list[ChatMessage]
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    tools: list | None = None
    tool_choice: Any = None
    response_format: dict | None = None
    stop: str | list[str] | None = None


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest) -> Any:
    candidates = _get_candidates(req.model)
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail=(
                f"No available providers for model '{req.model}'. "
                "Check config.yaml and registry."
            ),
        )

    extra = _build_extra_params(req)
    messages = [m.model_dump(exclude_none=True) for m in req.messages]

    if req.stream:
        return await _handle_streaming(candidates, messages, extra)

    return await _handle_non_streaming(candidates, messages, extra, req.model)


async def _handle_non_streaming(
    candidates: list[Candidate],
    messages: list[dict[str, Any]],
    extra: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    last_error: Exception | None = None

    for _ in range(MAX_RETRIES):
        candidate = scheduler.pick(candidates)
        if candidate is None:
            break

        start = time.time()
        try:
            resp = await call_provider(candidate, messages, stream=False, **extra)
            latency = (time.time() - start) * 1000
            scheduler.report_success(candidate, total_tokens=resp.total_tokens)
            log_decision(None, candidate, "success", latency, resp.total_tokens)
            return _format_response(resp.data, candidate)
        except Exception as e:
            latency = (time.time() - start) * 1000
            scheduler.report_failure(candidate)
            log_decision(None, candidate, "failure", latency, error=str(e))
            last_error = e
            continue

    detail = f"All providers exhausted after {MAX_RETRIES} retries."
    if last_error:
        detail += f" Last error: {last_error}"
    next_time = scheduler.get_next_available_time()
    headers = {}
    if next_time:
        retry_after = max(1, int(next_time - time.time()))
        headers["Retry-After"] = str(retry_after)

    raise HTTPException(status_code=429, detail=detail, headers=headers)


async def _handle_streaming(
    candidates: list[Candidate],
    messages: list[dict[str, Any]],
    extra: dict[str, Any],
) -> StreamingResponse:
    last_error: Exception | None = None

    for _ in range(MAX_RETRIES):
        candidate = scheduler.pick(candidates)
        if candidate is None:
            break

        try:
            stream = await call_provider_streaming(candidate, messages, **extra)
            scheduler.report_success(candidate, total_tokens=0)

            async def event_generator(s=stream):
                try:
                    async for chunk in s:
                        if hasattr(chunk, "model_dump_json"):
                            data = chunk.model_dump_json()
                        else:
                            data = json.dumps(chunk)
                        yield f"data: {data}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception:
                    yield "data: [DONE]\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        except Exception as e:
            scheduler.report_failure(candidate)
            last_error = e
            continue

    detail = f"All providers exhausted for streaming. Last error: {last_error}"
    raise HTTPException(status_code=429, detail=detail)


@router.get("/v1/models")
async def list_models() -> dict[str, Any]:
    registry = get_registry()
    config = get_config()

    enabled_providers = {k.provider for k in config.keys if k.enabled}
    logical_models = list(config.policies.keys())

    models = []
    for lm in logical_models:
        models.append({
            "id": lm,
            "object": "model",
            "owned_by": "free-llm-hub",
            "type": "logical",
        })

    seen = set()
    for entry in registry:
        if entry.provider in enabled_providers and entry.model not in seen:
            seen.add(entry.model)
            models.append({
                "id": entry.model,
                "object": "model",
                "owned_by": entry.provider,
                "type": "physical",
                "capabilities": entry.capabilities,
                "context_window": entry.context_window,
            })

    return {"object": "list", "data": models}


def _get_candidates(model: str) -> list[Candidate]:
    config = get_config()
    if model in config.policies or model == "auto":
        return resolve_candidates(model, config)
    return resolve_for_physical_model(model, config)


def _build_extra_params(req: ChatCompletionRequest) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if req.temperature is not None:
        extra["temperature"] = req.temperature
    if req.top_p is not None:
        extra["top_p"] = req.top_p
    if req.max_tokens is not None:
        extra["max_tokens"] = req.max_tokens
    if req.tools:
        extra["tools"] = req.tools
    if req.tool_choice is not None:
        extra["tool_choice"] = req.tool_choice
    if req.response_format:
        extra["response_format"] = req.response_format
    if req.stop:
        extra["stop"] = req.stop
    return extra


def _format_response(response: Any, candidate: Candidate) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif isinstance(response, dict):
        data = response
    else:
        data = {"raw": str(response)}

    data.setdefault("x_free_llm_hub", {
        "provider": candidate.provider,
        "model": candidate.model,
        "key_label": candidate.key_label,
    })
    return data

"""Admin API routes — /admin/quota, /admin/health, /admin/reload, /admin/ui."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import get_config, load_config
from app.core.health import get_probe
from app.core.quota import get_tracker
from app.core.registry import get_registry, load_registry

router = APIRouter(prefix="/admin", tags=["admin"])

_DASHBOARD_HTML = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")


@router.get("/ui", response_class=HTMLResponse)
async def admin_ui() -> str:
    """Read-only dashboard for quota and health."""
    return _DASHBOARD_HTML


@router.get("/quota")
async def get_quota() -> dict[str, Any]:
    """Return per-key, per-model quota status."""
    cfg = get_config()
    tracker = get_tracker()
    registry = get_registry()

    enabled_keys = [k for k in cfg.keys if k.enabled]
    key_models: dict[str, list[dict[str, Any]]] = {}

    for kc in enabled_keys:
        key_id = f"{kc.provider}:{kc.label}"
        provider_entries = [e for e in registry if e.provider == kc.provider]
        models_status = []

        for entry in provider_entries:
            rl = entry.rate_limit
            status = tracker.check_quota(
                provider=kc.provider,
                key_label=kc.label,
                model=entry.model,
                rpm=rl.rpm,
                rpd=rl.rpd,
                tpm=rl.tpm,
                tpd=rl.tpd,
            )
            models_status.append({
                "model": entry.model,
                "requests_used": status.requests_used,
                "requests_limit": status.requests_limit,
                "requests_remaining": status.requests_remaining,
                "tokens_used": status.tokens_used,
                "tokens_limit": status.tokens_limit,
                "tokens_remaining": status.tokens_remaining,
                "ok": status.ok,
                "resets_in_seconds": status.resets_in_seconds,
            })

        key_models[key_id] = models_status

    return {"quotas": key_models}


@router.get("/health")
async def get_health() -> dict[str, Any]:
    """Return per-key health probe state."""
    probe = get_probe()
    states = probe.all_states()
    out: dict[str, dict[str, Any]] = {}
    for key_id, st in states.items():
        out[key_id] = {
            "status": st.status,
            "last_check_at": st.last_check_at,
            "last_latency_ms": st.last_latency_ms,
            "consecutive_failures": st.consecutive_failures,
            "last_error": st.last_error,
        }
    return {"health": out}


@router.post("/probe")
async def trigger_probe() -> dict[str, str]:
    """Trigger an immediate health probe pass."""
    probe = get_probe()
    await probe.probe_once()
    return {"status": "probed"}


@router.post("/reload")
async def admin_reload() -> dict[str, str]:
    load_config()
    load_registry()
    return {"status": "reloaded"}


@router.post("/compact")
async def admin_compact() -> dict[str, int]:
    """Remove old quota events to keep SQLite small."""
    tracker = get_tracker()
    removed = tracker.compact()
    return {"removed_events": removed}

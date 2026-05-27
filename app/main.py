"""FastAPI entrypoint for free-llm-hub."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from . import __version__
from .api.admin import router as admin_router
from .api.routes import router as api_router
from .core.config import load_config
from .core.health import get_probe, init_probe
from .core.metrics import metrics
from .core.quota import init_tracker
from .core.registry import load_registry
from .core.reloader import get_reloader, init_reloader


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = load_config()
    load_registry()
    init_tracker(backend=cfg.storage.backend, url=cfg.storage.url)

    interval = float(os.environ.get("FREELLM_PROBE_INTERVAL", "300"))
    probe = init_probe(interval_seconds=interval)
    if os.environ.get("FREELLM_DISABLE_PROBE", "0") != "1":
        probe.start()

    reload_interval = float(os.environ.get("FREELLM_RELOADER_INTERVAL", "2"))
    reloader = init_reloader(interval_seconds=reload_interval)
    if os.environ.get("FREELLM_DISABLE_RELOADER", "0") != "1":
        reloader.start()
    yield
    await get_probe().stop()
    await get_reloader().stop()


app = FastAPI(title="free-llm-hub", version=__version__, lifespan=lifespan)
app.include_router(api_router)
app.include_router(admin_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    return metrics.render()

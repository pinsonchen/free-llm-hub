"""FastAPI entrypoint for free-llm-hub."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .api.routes import router as api_router
from .core.config import load_config
from .core.registry import load_registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    load_config()
    load_registry()
    yield


app = FastAPI(title="free-llm-hub", version=__version__, lifespan=lifespan)
app.include_router(api_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/admin/reload")
async def admin_reload() -> dict[str, str]:
    load_config()
    load_registry()
    return {"status": "reloaded"}

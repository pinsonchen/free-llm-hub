"""FastAPI entrypoint for free-llm-hub."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .api.admin import router as admin_router
from .api.routes import router as api_router
from .core.config import load_config
from .core.quota import init_tracker
from .core.registry import load_registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = load_config()
    load_registry()
    db_url = cfg.storage.url
    db_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else "hub.db"
    init_tracker(db_path)
    yield


app = FastAPI(title="free-llm-hub", version=__version__, lifespan=lifespan)
app.include_router(api_router)
app.include_router(admin_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}

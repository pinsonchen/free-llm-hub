"""FastAPI entrypoint. M1 will fill this in; for now it exposes a healthcheck
so the project skeleton boots cleanly."""

from fastapi import FastAPI

from . import __version__

app = FastAPI(title="free-llm-hub", version=__version__)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}

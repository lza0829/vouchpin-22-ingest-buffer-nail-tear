from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import PROJECT_NAME
from app.seed import seed_if_empty
from app.services.buffer_service import worker
from app.routers import dashboard, events, redeem, settings

seed_if_empty()


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker.start()
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(title=PROJECT_NAME, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(dashboard.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(redeem.router, prefix="/api")
app.include_router(settings.router, prefix="/api")

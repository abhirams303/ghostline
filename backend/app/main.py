from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analyze import router as analyze_router
from app.api.health import router as health_router
from app.api.stream import router as stream_router
from app.config import get_settings
from app.storage import initialize_storage


def create_app() -> FastAPI:
    settings = get_settings()
    initialize_storage(settings.database_path)
    app = FastAPI(
        title=settings.app_name,
        description="Defensive OSINT synthesis service for OPSEC Mirror.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(analyze_router)
    app.include_router(stream_router)
    return app


app = create_app()

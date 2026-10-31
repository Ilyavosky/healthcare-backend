from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.routers import config, health, rooms, scenarios, solve
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Healthcare API",
        description="Priorización de urgencias médicas con Costo Uniforme y A*",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    for module in (health, config, scenarios, solve, rooms):
        app.include_router(module.router, prefix="/api")
    if settings is not get_settings():
        app.dependency_overrides[get_settings] = lambda: settings
    return app


app = create_app()

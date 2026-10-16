"""FastAPI app factory: CORS, error envelope, routers."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from coach_core.errors import ApiError, BudgetExceeded, error_body
from coach_core.logging_setup import RequestLogMiddleware, setup_logging
from skillcoach_api.config import get_settings
from skillcoach_api.routes import (
    chat,
    checkins,
    health,
    internal,
    notifications,
    profile,
    progress,
    skills,
)
from skillcoach_api.services.container import build_services


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    application = FastAPI(title="Skill Coach API", version="0.1.0")
    application.state.services = build_services(settings)
    application.add_middleware(RequestLogMiddleware)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        resets_at = exc.resets_at if isinstance(exc, BudgetExceeded) else None
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message_key, resets_at=resets_at),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content=error_body("validation_error", "errors.validation")
        )

    @application.exception_handler(Exception)
    async def internal_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content=error_body("internal", "errors.internal"))

    application.include_router(health.router)
    application.include_router(chat.router)
    application.include_router(profile.router)
    application.include_router(skills.router)
    application.include_router(notifications.router)
    application.include_router(internal.router)
    application.include_router(progress.router)
    application.include_router(checkins.router)
    return application


app = create_app()

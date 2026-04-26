"""FastAPI application factory.

Endpoints (all under /api/v1):
- POST /uploads                  CSV upload → pending leads
- POST /runs/trigger             manual pipeline trigger (background task)
- GET  /runs                     run history (paginated)
- GET  /runs/{id}                run detail + MD report
- GET  /leads                    list with tier/status/run filters
- GET  /leads/{id}               full detail with provenance/score/email/feedback
- POST /leads/{id}/feedback      one-click approve/edit/reject
- GET  /metrics/overview         KPIs + 7-day trend + tier distribution
- GET  /metrics/api-performance  per-API avg/p95/failures
- GET  /healthz                  liveness probe (no DB dependency)

OpenAPI / Swagger UI auto-published at /docs (and /redoc).
The React frontend uses openapi-typescript to derive types from /openapi.json.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from elise_leads import __version__
from elise_leads.api.routers import (
    feedback as feedback_router,
    leads as leads_router,
    metrics as metrics_router,
    runs as runs_router,
    uploads as uploads_router,
    webhooks as webhooks_router,
)
from elise_leads.enrichers._http import close_http_client
from elise_leads.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks. We don't open the DB engine here because it's
    eagerly created at module import; we DO ensure the shared httpx client
    is closed on shutdown so connections don't leak.
    """
    yield
    await close_http_client()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EliseAI Lead Pipeline API",
        version=__version__,
        description=(
            "REST API powering the EliseAI inbound lead enrichment dashboard. "
            "Pairs with the daily cron pipeline; both share the same Postgres DB."
        ),
        lifespan=lifespan,
    )

    # CORS — allow the React dev server + production Vercel domain
    cors_origins = [settings.frontend_url]
    if settings.is_production:
        # Add wildcard subdomain on Vercel preview deploys
        cors_origins.append("https://*.vercel.app")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Liveness probe — does NOT touch the DB so an outage of Neon doesn't make
    # this health check fail and trigger restart loops on Render.
    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "env": settings.environment}

    # Versioned API routers
    api_prefix = "/api/v1"
    app.include_router(uploads_router.router, prefix=api_prefix)
    app.include_router(webhooks_router.router, prefix=api_prefix)
    app.include_router(runs_router.router, prefix=api_prefix)
    app.include_router(leads_router.router, prefix=api_prefix)
    app.include_router(feedback_router.router, prefix=api_prefix)
    app.include_router(metrics_router.router, prefix=api_prefix)

    return app


# Eagerly create the app instance so `uvicorn elise_leads.api.main:app` works
app = create_app()

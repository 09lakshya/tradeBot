"""FastAPI application factory."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, create_engine, text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.redis import get_redis

log = get_logger(__name__)

# Bound on the readiness DB probe. A health check must fail fast: without an
# explicit connect timeout a dead/filtered Postgres lets the TCP SYN retransmit
# for the OS default (~21s on Windows), so the probe hangs instead of returning
# 503 promptly. This dedicated engine keeps that timeout off the app's main pool.
_PROBE_CONNECT_TIMEOUT_S = 2


@lru_cache
def _probe_engine() -> Engine:
    return create_engine(
        settings.database_url,
        connect_args={"connect_timeout": _PROBE_CONNECT_TIMEOUT_S},
        pool_pre_ping=True,
        future=True,
    )


def _check_database() -> tuple[bool, str]:
    """Round-trip a trivial query so readiness reflects real connectivity."""
    try:
        with _probe_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - report, never crash the probe
        return False, str(exc)


def _check_redis() -> tuple[bool, str]:
    """Redis is an accelerator, not a hard dependency: report but don't fail on it."""
    client = get_redis()
    if client is None:
        return False, "unreachable"
    try:
        client.ping()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings.app_debug)
    log.info("startup", env=settings.app_env, provider=settings.market_data_provider)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Trade Bot API",
        version="0.1.0",
        description="Autonomous AI trading platform — paper trading phase.",
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Liveness: the process is up and serving. No dependency checks."""
        return {"status": "ok", "env": settings.app_env}

    @app.get("/health/ready", tags=["system"])
    def readiness() -> JSONResponse:
        """Readiness: verify the stack this service depends on.

        Postgres is required — its failure returns 503 so an orchestrator holds
        traffic. Redis is a cache accelerator, so its absence is reported as
        ``degraded`` but never fails readiness (the app serves from the DB).
        """
        db_ok, db_detail = _check_database()
        redis_ok, redis_detail = _check_redis()
        status = "ok" if db_ok else "unavailable"
        if db_ok and not redis_ok:
            status = "degraded"
        body = {
            "status": status,
            "checks": {
                "database": {"ok": db_ok, "detail": db_detail},
                "redis": {"ok": redis_ok, "detail": redis_detail},
            },
        }
        return JSONResponse(body, status_code=200 if db_ok else 503)

    return app


app = create_app()

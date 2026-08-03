"""Aggregate v1 API router. Domain routers are mounted here as they come online."""
from fastapi import APIRouter

from app.domains.market_data.router import router as market_data_router
from app.domains.trading.router import router as trading_router

api_router = APIRouter()

api_router.include_router(market_data_router, prefix="/market-data", tags=["market-data"])
api_router.include_router(trading_router, prefix="/trading", tags=["trading"])

# Mounted incrementally (correctness-first build order):
# ... risk, strategies, backtest, metrics, platform


@api_router.get("/ping", tags=["system"])
def ping() -> dict[str, str]:
    return {"message": "pong"}

"""Aggregate v1 API router. Domain routers are mounted here as they come online."""
from fastapi import APIRouter

from app.domains.analytics.router import router as analytics_router
from app.domains.backtest.router import router as backtest_router
from app.domains.market_data.router import router as market_data_router
from app.domains.operations.router import router as operations_router
from app.domains.orchestrator.router import router as orchestrator_router
from app.domains.platform.router import router as platform_router
from app.domains.portfolio.router import router as portfolio_router
from app.domains.risk.router import router as risk_router
from app.domains.strategies.router import router as strategies_router
from app.domains.trading.router import router as trading_router

api_router = APIRouter()

api_router.include_router(market_data_router, prefix="/market-data", tags=["market-data"])
api_router.include_router(trading_router, prefix="/trading", tags=["trading"])
api_router.include_router(risk_router, prefix="", tags=["risk"])
api_router.include_router(backtest_router, prefix="/backtest", tags=["backtest"])
api_router.include_router(strategies_router, prefix="", tags=["strategies"])
api_router.include_router(portfolio_router, prefix="", tags=["portfolio-construction"])
api_router.include_router(orchestrator_router, prefix="", tags=["orchestrator"])
api_router.include_router(platform_router, prefix="", tags=["platform-observability"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(operations_router, prefix="", tags=["operations"])



@api_router.get("/ping", tags=["system"])
def ping() -> dict[str, str]:
    return {"message": "pong"}

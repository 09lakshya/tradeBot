"""FastAPI REST API Endpoints for Strategy Discovery, Validation, and Lifecycle."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.strategies.exceptions import (
    InvalidStrategyParameterError,
    StrategyNotFoundError,
    StrategyValidationError,
)
from app.domains.strategies.models import StrategyParameterSnapshotModel
from app.domains.strategies.registry import StrategyRegistry
from app.domains.strategies.schemas import (
    ParameterSnapshotCreate,
    ParameterSnapshotResponse,
    StrategyMetadata,
    StrategyParameterValidationRequest,
    StrategyParameterValidationResponse,
)
from app.domains.strategies.service import StrategyService

router = APIRouter(prefix="/strategies", tags=["Strategies"])


@router.get("", response_model=list[StrategyMetadata])
def list_strategies(db: Session = Depends(get_db)):
    """List all available registered institutional strategies."""
    service = StrategyService(db)
    strategies = service.list_strategies()
    # Sync with DB if needed
    for strat in strategies:
        service.register_or_update_strategy_in_db(strat)
    return strategies


@router.get("/{strategy_id}", response_model=StrategyMetadata)
def get_strategy(strategy_id: str, version: str | None = None, db: Session = Depends(get_db)):
    """Retrieve metadata and schema for a specific strategy."""
    service = StrategyService(db)
    try:
        return service.get_strategy(strategy_id, version)
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{strategy_id}/parameters")
def get_strategy_parameters(strategy_id: str, version: str | None = None):
    """Retrieve default parameters and JSON parameter schema."""
    try:
        strat_cls = StrategyRegistry.get_strategy_class(strategy_id, version)
        return {
            "strategy_id": strategy_id,
            "version": strat_cls.version,
            "default_parameters": strat_cls.default_parameters,
            "parameter_schema": strat_cls.get_parameter_schema(),
        }
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{strategy_id}/validate", response_model=StrategyParameterValidationResponse)
def validate_parameters(strategy_id: str, req: StrategyParameterValidationRequest):
    """Validate strategy parameter payload."""
    try:
        strat_cls = StrategyRegistry.get_strategy_class(strategy_id)
        validated = strat_cls.validate_parameters(req.parameters)
        return StrategyParameterValidationResponse(
            is_valid=True,
            validated_parameters=validated,
            errors=[],
        )
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidStrategyParameterError, StrategyValidationError) as e:
        return StrategyParameterValidationResponse(
            is_valid=False,
            validated_parameters={},
            errors=[str(e)],
        )


@router.post("/{strategy_id}/snapshots", response_model=ParameterSnapshotResponse, status_code=status.HTTP_201_CREATED)
def create_parameter_snapshot(
    strategy_id: str,
    req: ParameterSnapshotCreate,
    db: Session = Depends(get_db),
):
    """Create an immutable parameter snapshot for a strategy."""
    service = StrategyService(db)
    try:
        snapshot = service.create_parameter_snapshot(
            strategy_id=strategy_id,
            parameters=req.parameters,
            description=req.description,
            created_by=req.created_by,
        )
        return ParameterSnapshotResponse(
            id=snapshot.id,
            strategy_id=snapshot.strategy_id,
            version=snapshot.version,
            parameters=snapshot.parameters,
            description=snapshot.description,
            created_by=snapshot.created_by,
            created_at=snapshot.created_at,
        )
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{strategy_id}/snapshots", response_model=list[ParameterSnapshotResponse])
def list_parameter_snapshots(strategy_id: str, db: Session = Depends(get_db)):
    """List all parameter snapshots for a strategy."""
    snapshots = (
        db.query(StrategyParameterSnapshotModel)
        .filter(StrategyParameterSnapshotModel.strategy_id == strategy_id)
        .order_by(StrategyParameterSnapshotModel.created_at.desc())
        .all()
    )
    return [
        ParameterSnapshotResponse(
            id=s.id,
            strategy_id=s.strategy_id,
            version=s.version,
            parameters=s.parameters,
            description=s.description,
            created_by=s.created_by,
            created_at=s.created_at,
        )
        for s in snapshots
    ]

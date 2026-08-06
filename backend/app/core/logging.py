"""Structured JSON logging with correlation IDs and platform observability bridge."""
from __future__ import annotations

import logging
import sys

from app.domains.platform.logging import StructuredLogger, get_structured_logger


def configure_logging(debug: bool = False) -> None:
    """Configures root logging level and stream handler."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )


def get_logger(name: str) -> StructuredLogger:
    """Returns a production-grade StructuredLogger with ContextVar propagation."""
    return get_structured_logger(name)


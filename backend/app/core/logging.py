"""Structured JSON logging with correlation IDs."""
from __future__ import annotations

import logging
import sys

try:
    import structlog

    def configure_logging(debug: bool = False) -> None:
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

    def get_logger(name: str) -> structlog.stdlib.BoundLogger:
        return structlog.get_logger(name)

except ImportError:  # pragma: no cover
    class _FallbackLogger:
        def __init__(self, logger: logging.Logger) -> None:
            self._logger = logger

        def debug(self, msg: str, **kwargs: object) -> None:
            self._logger.debug(f"{msg} {kwargs}" if kwargs else msg)

        def info(self, msg: str, **kwargs: object) -> None:
            self._logger.info(f"{msg} {kwargs}" if kwargs else msg)

        def warning(self, msg: str, **kwargs: object) -> None:
            self._logger.warning(f"{msg} {kwargs}" if kwargs else msg)

        def error(self, msg: str, **kwargs: object) -> None:
            self._logger.error(f"{msg} {kwargs}" if kwargs else msg)

        def exception(self, msg: str, **kwargs: object) -> None:
            self._logger.exception(f"{msg} {kwargs}" if kwargs else msg)

        def bind(self, **kwargs: object) -> _FallbackLogger:
            return self

    def configure_logging(debug: bool = False) -> None:
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", stream=sys.stdout, level=level)

    def get_logger(name: str) -> object:
        return _FallbackLogger(logging.getLogger(name))

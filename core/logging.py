"""Structured-ish logging setup. Called once at process start."""

import logging
import sys

from core.config import get_settings

_FORMAT = "%(asctime)s %(levelname)-8s %(name)-28s %(message)s"


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format=_FORMAT,
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

"""Helper setup logging dengan format hybrid (text untuk dev, JSON untuk produksi)."""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from app.config import settings

_TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logger(name: str) -> logging.Logger:
    """Bangun logger dengan format sesuai env var LOG_FORMAT.

    Args:
        name: Nama logger, biasanya __name__ dari module pemanggil.

    Returns:
        Logger yang sudah punya handler stdout; pemanggilan berulang tidak
        menambah handler duplikat.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)

    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter(_JSON_FORMAT))
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))

    logger.addHandler(handler)
    logger.propagate = False
    return logger

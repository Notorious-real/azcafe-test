# ============================================================
#  AZ Cafe - Logging
#  One rotating log file per machine, written to the data folder.
#  Both apps call setup_logging() first thing at startup, so a
#  "--windowed" build still explains itself when something breaks.
# ============================================================

import logging
import sys
from logging.handlers import RotatingFileHandler

import paths

_configured = False


def setup_logging(name: str = "azcafe", level=logging.INFO) -> logging.Logger:
    global _configured
    if _configured:
        return logging.getLogger(name)

    logger = logging.getLogger()
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")

    try:
        log_file = paths.data_path("logs", f"{name}.log")
        handler = RotatingFileHandler(log_file, maxBytes=1_000_000,
                                      backupCount=5, encoding="utf-8")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    except OSError:
        pass

    # A console handler only helps when there is a console (dev runs).
    if sys.stderr is not None and getattr(sys.stderr, "isatty", lambda: False)():
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        logger.addHandler(stream)

    _configured = True
    logger.info("── %s logging started ──", name)
    return logging.getLogger(name)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_path() -> str:
    return paths.data_path("logs", "azcafe.log")

from __future__ import annotations

import logging
import sys


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger("droidnote")
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(handler)
    # Never attach transcript/audio payloads to log records in this process.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"droidnote.{name}")

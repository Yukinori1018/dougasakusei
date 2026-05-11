"""Rich console logger."""
from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%H:%M:%S]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

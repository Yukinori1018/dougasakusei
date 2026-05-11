"""Generic file IO helpers."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, BaseModel):
        path.write_text(obj.model_dump_json(indent=2), encoding="utf-8")
        return
    if isinstance(obj, list) and obj and isinstance(obj[0], BaseModel):
        obj = [o.model_dump(mode="json") for o in obj]
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

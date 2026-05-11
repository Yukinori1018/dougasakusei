"""Project path helpers — one source of truth for the on-disk layout."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..settings import REPO_ROOT, env

SUBDIRS = (
    "research/raw",
    "script",
    "audio/ai_segments",
    "audio/user_segments",
    "visuals/broll",
    "visuals/charts",
    "visuals/thumbnails",
    "subtitles",
    "bgm",
    "metadata",
    "compliance",
    "timeline",
    "output/shorts",
)


def projects_root() -> Path:
    p = REPO_ROOT / env().PROJECTS_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def new_project_dir(slug: str) -> Path:
    name = f"{date.today().isoformat()}_{slug}"
    p = projects_root() / name
    for sd in SUBDIRS:
        (p / sd).mkdir(parents=True, exist_ok=True)
    return p


def project_dir(name: str) -> Path:
    return projects_root() / name


def rel(project_dir: Path, full: Path) -> str:
    try:
        return str(full.relative_to(project_dir))
    except ValueError:
        return str(full)

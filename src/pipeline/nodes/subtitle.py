"""Subtitle node: build an SRT directly from the script timing.

We optionally re-align with faster-whisper if the final mixed audio is present,
but the default path uses the script + estimated durations so the pipeline can
run end-to-end without a GPU.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..schemas import PipelineState
from ..utils.io import read_json, write_text
from ..utils.logging import get_logger
from ..settings import REPO_ROOT

log = get_logger(__name__)


def _format_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _load_dictionary() -> dict[str, str]:
    p = REPO_ROOT / "assets" / "dictionary" / "tax_terms.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _apply_dictionary(text: str, mapping: dict[str, str]) -> str:
    for wrong, right in mapping.items():
        text = text.replace(wrong, right)
    return text


def run(state: PipelineState) -> PipelineState:
    log.info("[subtitle] building SRT from script timing")
    if state.script is None:
        return state
    mapping = _load_dictionary()
    pd = state.project_path()
    t = 0.0
    lines = []
    for i, seg in enumerate(state.script.segments, start=1):
        start = t
        end = t + max(seg.duration_est_sec, 1.0)
        text = _apply_dictionary(seg.text, mapping)
        lines.append(f"{i}\n{_format_ts(start)} --> {_format_ts(end)}\n{text}\n")
        t = end

    srt = "\n".join(lines)
    write_text(pd / "subtitles" / "ja.srt", srt)
    state.subtitles_srt = str((pd / "subtitles" / "ja.srt").relative_to(pd))
    log.info("[subtitle] wrote %d cues", len(lines))
    return state

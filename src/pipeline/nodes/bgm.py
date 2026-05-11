"""BGM node: pick a track from the local licensed library by tag match (no SaaS API)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..schemas import PipelineState
from ..settings import REPO_ROOT, config
from ..utils.io import write_json
from ..utils.llm import call_json
from ..utils.logging import get_logger

log = get_logger(__name__)


def _load_library() -> list[dict]:
    p = REPO_ROOT / config()["bgm"]["metadata_file"]
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("tracks", [])
    except Exception:
        return []


def run(state: PipelineState) -> PipelineState:
    log.info("[bgm] choosing track from local library")
    tracks = _load_library()
    pd = state.project_path()
    out = pd / "bgm" / "selection.json"

    if not tracks:
        log.warning("[bgm] library is empty. Add licensed tracks under %s", config()["bgm"]["library_dir"])
        write_json(out, {"selected": None, "reason": "empty library"})
        return state

    summary = state.script.summary if state.script else state.config.topic
    system = (
        "視聴者の感情に合うBGMを下記のライブラリから1つだけ選び、JSON で id を返してください。"
        "落ち着き／信頼感／集中に向くものを優先。"
    )
    user = json.dumps({"summary": summary, "tracks": tracks}, ensure_ascii=False)
    pick = call_json(system=system, user=user, tier=config()["models"]["metadata"]).get("id")
    chosen = next((t for t in tracks if t.get("id") == pick), tracks[0])

    src = REPO_ROOT / chosen["file"]
    dst = pd / "bgm" / Path(chosen["file"]).name
    if src.exists():
        shutil.copy2(src, dst)
        state.bgm_path = str(dst.relative_to(pd))
    write_json(out, {"selected": chosen})
    log.info("[bgm] selected %s", chosen.get("id"))
    return state

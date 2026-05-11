"""Shorts node: surface 5 candidates from the long-form script for human selection."""
from __future__ import annotations

from ..schemas import PipelineState, ShortCandidate
from ..settings import config
from ..utils.io import write_json, write_text
from ..utils.llm import call_json
from ..utils.logging import get_logger

log = get_logger(__name__)


def run(state: PipelineState) -> PipelineState:
    log.info("[shorts] extracting candidate clips")
    if state.script is None:
        return state
    cfg = config()
    target = cfg["shorts"]["target_duration_sec"]
    n = cfg["shorts"]["candidates_per_long"]

    payload = []
    cursor = 0.0
    for seg in state.script.segments:
        payload.append(
            {"idx": seg.idx, "start": cursor, "end": cursor + seg.duration_est_sec, "text": seg.text}
        )
        cursor += seg.duration_est_sec

    system = (
        f"次の動画台本から、{target}秒前後で完結する強力な切り出し候補を {n} 個抽出してください。"
        "数値インパクト・体験談・結論の3パターンを優先。出力は JSON のみ。"
    )
    user = (
        f"JSON keys: candidates[{n}] (各: idx, start_sec, end_sec, hook, rationale)\n\n"
        f"segments: {payload}"
    )
    data = call_json(system=system, user=user, tier=cfg["models"]["metadata"])

    candidates = [ShortCandidate(**c) for c in data.get("candidates", [])]
    state.shorts = candidates

    pd = state.project_path()
    write_json(pd / "output" / "shorts" / "candidates.json", candidates)
    write_text(
        pd / "output" / "shorts" / "PICK_ME.md",
        "# ショート候補（採用したい番号を選択）\n\n"
        + "\n".join(
            f"## 候補 {c.idx}: {c.hook}\n- 開始: {c.start_sec:.0f}s / 終了: {c.end_sec:.0f}s\n- 根拠: {c.rationale}\n"
            for c in candidates
        ),
    )
    log.info("[shorts] %d candidates produced", len(candidates))
    return state

"""Revisor: feed compliance warnings back into the script and rewrite flagged segments.

Runs after compliance. Only rewrites segments that are explicitly referenced by a
warn/block finding (by `idx:N` in detail/suggestion) or by a high-severity factcheck
issue. Stays cheap by using the script's tier and only patching affected segments.
"""
from __future__ import annotations

import re

from ..schemas import PipelineState, Script
from ..settings import config
from ..utils.io import write_json, write_text
from ..utils.llm import call_llm
from ..utils.logging import get_logger

log = get_logger(__name__)


_IDX_PATTERN = re.compile(r"idx[:\s]*(\d+)", re.IGNORECASE)


def _extract_target_indices(state: PipelineState) -> dict[int, list[str]]:
    """Map segment_idx → list of issue descriptions to address."""
    targets: dict[int, list[str]] = {}

    if state.compliance:
        for f in state.compliance.findings:
            if f.severity not in ("warn", "block"):
                continue
            text = f"{f.detail} {f.suggestion}"
            for m in _IDX_PATTERN.finditer(text):
                idx = int(m.group(1))
                targets.setdefault(idx, []).append(
                    f"[{f.check}/{f.severity}] {f.detail} → {f.suggestion}"
                )

    if state.factcheck:
        for i in state.factcheck.issues:
            if i.severity == "high":
                targets.setdefault(i.segment_idx, []).append(
                    f"[factcheck/high] {i.reason} → {i.suggested_fix}"
                )

    return targets


def _rewrite_segment(original_text: str, issues: list[str]) -> str:
    system = (
        "あなたは YouTube 台本の校閲者です。指摘事項を反映して本文を書き直してください。"
        "意味と長さはほぼ維持。口語のまま。出力は本文のみで前置き不要。"
        "断定的表現は避け、必要に応じて『顧問税理士にご相談ください』等の留保を入れる。"
        "『お客様の事例』『実際のクライアント』等の表現は『モデルケース』『仮定の例』に置き換える。"
    )
    user = "指摘事項:\n" + "\n".join(f"- {x}" for x in issues) + f"\n\n本文:\n{original_text}"
    return call_llm(
        system=system,
        user=user,
        tier=config()["models"]["script_oralize"],
        max_tokens=2000,
        temperature=0.3,
    ).strip()


def run(state: PipelineState) -> PipelineState:
    log.info("[revisor] checking for compliance warnings to address")
    if state.script is None:
        return state

    targets = _extract_target_indices(state)
    if not targets:
        log.info("[revisor] no warnings reference specific segments — skipping")
        return state

    log.info("[revisor] rewriting %d segments: %s", len(targets), sorted(targets.keys()))
    pd = state.project_path()
    changes: list[dict] = []

    for seg in state.script.segments:
        if seg.idx not in targets:
            continue
        original = seg.text
        try:
            revised = _rewrite_segment(original, targets[seg.idx])
        except Exception as e:  # noqa: BLE001
            log.warning("[revisor] segment %d rewrite failed: %s", seg.idx, e)
            continue
        if revised and revised != original:
            seg.text = revised
            changes.append(
                {
                    "idx": seg.idx,
                    "issues": targets[seg.idx],
                    "before": original,
                    "after": revised,
                }
            )

    write_json(pd / "compliance" / "revisor_changes.json", changes)
    if changes:
        lines = ["# Revisor 適用結果\n"]
        for c in changes:
            lines.append(f"## seg {c['idx']}\n")
            lines.append("**指摘:**\n" + "\n".join(f"- {x}" for x in c["issues"]) + "\n")
            lines.append(f"**Before:**\n> {c['before']}\n")
            lines.append(f"**After:**\n> {c['after']}\n")
        write_text(pd / "compliance" / "revisor_changes.md", "\n".join(lines))

        # Re-write script artifacts so script.md / teleprompter.html reflect the changes.
        from . import script as script_node
        script_node._persist(state, state.script)

    log.info("[revisor] applied %d rewrites", len(changes))
    return state

"""Fact-checking: cross-reference every claim with primary-source URLs."""
from __future__ import annotations

from ..schemas import FactCheckIssue, FactCheckReport, PipelineState
from ..settings import config
from ..utils.io import write_json, write_text
from ..utils.llm import call_json
from ..utils.logging import get_logger

log = get_logger(__name__)


def run(state: PipelineState) -> PipelineState:
    log.info("[factcheck] verifying claims")
    script = state.script
    if script is None:
        state.factcheck = FactCheckReport()
        return state

    claims_payload = []
    for seg in script.segments:
        for c in seg.claims:
            claims_payload.append(
                {"segment_idx": seg.idx, "text": c.text, "sources": c.source_urls}
            )

    system = (
        "あなたはファクトチェッカーです。出力は JSON のみ。"
        "各 claim について、source_urls が一次ソース（nta.go.jp / chusho.meti.go.jp / e-gov.go.jp 等）か、"
        "claim と source が論理的に整合しているかを評価してください。"
        "不確実・要再確認の場合は high/medium severity で issues に列挙。"
    )
    user = (
        "JSON keys: issues (各: segment_idx, claim, severity (low|medium|high), reason, suggested_fix), "
        "verified_claim_count (int), needs_human_review (bool)\n\n"
        f"claims: {claims_payload}"
    )
    tier = config()["models"]["factcheck"]
    data = call_json(system=system, user=user, tier=tier)

    report = FactCheckReport(
        issues=[FactCheckIssue(**i) for i in data.get("issues", [])],
        verified_claim_count=data.get("verified_claim_count", 0),
        needs_human_review=data.get("needs_human_review", True),
        primary_source_urls=sorted(
            {url for seg in script.segments for c in seg.claims for url in c.source_urls}
        ),
    )

    # Promote to Opus if there are high-severity issues.
    if any(i.severity == "high" for i in report.issues):
        log.info("[factcheck] high-severity issues found → re-run with opus tier")
        data2 = call_json(system=system, user=user, tier=config()["models"]["factcheck_hard"])
        if data2.get("issues") is not None:
            report.issues = [FactCheckIssue(**i) for i in data2.get("issues", [])]
            report.needs_human_review = True

    pd = state.project_path()
    write_json(pd / "compliance" / "factcheck.json", report)
    write_text(
        pd / "compliance" / "citations.md",
        "# 引用元一覧（人間レビュー必須）\n\n"
        + "\n".join(f"- {u}" for u in report.primary_source_urls),
    )

    state.factcheck = report
    log.info(
        "[factcheck] %d verified, %d issues (review=%s)",
        report.verified_claim_count,
        len(report.issues),
        report.needs_human_review,
    )
    return state

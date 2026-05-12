"""Fact-checking: cross-reference every claim with primary-source URLs."""
from __future__ import annotations

from ..schemas import FactCheckIssue, FactCheckReport, PipelineState
from ..settings import config
from ..utils.io import write_json, write_text
from ..utils.llm import call_json
from ..utils.logging import get_logger
from ..utils.urlcheck import check_url_alive

log = get_logger(__name__)


def _verify_source_urls(state: PipelineState) -> list[FactCheckIssue]:
    """Probe every cited URL. Differentiates anti-bot 403 on trusted gov hosts
    (medium severity, manual review) from genuinely dead URLs (high severity)."""
    issues: list[FactCheckIssue] = []
    if state.script is None:
        return issues
    seen: dict[str, tuple[str, int]] = {}
    for seg in state.script.segments:
        for c in seg.claims:
            for url in c.source_urls:
                if url not in seen:
                    seen[url] = check_url_alive(url)
                status, code = seen[url]
                if status == "alive":
                    continue
                if status == "trusted":
                    issues.append(
                        FactCheckIssue(
                            segment_idx=seg.idx,
                            claim=c.text[:120],
                            severity="medium",
                            reason=(
                                f"出典URLは政府系一次ソース許可リストに該当しますが、"
                                f"サーバが自動アクセスを拒否しました (HTTP {code or 'n/a'}): {url}。"
                                f"ブラウザで実在性と内容を手動確認してください。"
                            ),
                            suggested_fix="ブラウザでURLを開き、参照箇所の見出し/日付を確認のうえ承認。",
                        )
                    )
                else:  # dead / unreachable
                    issues.append(
                        FactCheckIssue(
                            segment_idx=seg.idx,
                            claim=c.text[:120],
                            severity="high",
                            reason=f"出典URLにアクセス不可 ({code or status}): {url}",
                            suggested_fix="代替の一次ソースURLに差し替える",
                        )
                    )
    log.info("[factcheck] verified %d unique URLs, %d issues", len(seen), len(issues))
    return issues


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

    llm_issues = [FactCheckIssue(**i) for i in data.get("issues", [])]
    url_probe_issues = _verify_source_urls(state)

    report = FactCheckReport(
        issues=llm_issues + url_probe_issues,
        verified_claim_count=data.get("verified_claim_count", 0),
        needs_human_review=data.get("needs_human_review", True) or bool(llm_issues or url_probe_issues),
        primary_source_urls=sorted(
            {url for seg in script.segments for c in seg.claims for url in c.source_urls}
        ),
    )

    # Promote to Opus if the cheaper tier flagged high-severity issues; URL
    # probe issues are deterministic and preserved across the rerun.
    if any(i.severity == "high" for i in llm_issues):
        log.info("[factcheck] high-severity issues found → re-run with opus tier")
        data2 = call_json(system=system, user=user, tier=config()["models"]["factcheck_hard"])
        if data2.get("issues") is not None:
            report.issues = [FactCheckIssue(**i) for i in data2.get("issues", [])] + url_probe_issues
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

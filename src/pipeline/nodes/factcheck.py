"""Fact-checking: cross-reference every claim with primary-source URLs."""
from __future__ import annotations

import httpx

from ..schemas import FactCheckIssue, FactCheckReport, PipelineState
from ..settings import config
from ..utils.io import write_json, write_text
from ..utils.llm import call_json
from ..utils.logging import get_logger

log = get_logger(__name__)


def _check_url_alive(url: str) -> tuple[bool, int]:
    """HEAD with GET fallback. Detects 404-page redirects. Returns (is_alive, status_code)."""
    headers = {"User-Agent": "dougasakusei-factcheck/0.1"}
    try:
        with httpx.Client(timeout=8, follow_redirects=True, headers=headers) as c:
            r = c.head(url)
            if r.status_code >= 400 or r.status_code == 405:
                r = c.get(url)
            if r.status_code >= 400:
                return False, r.status_code
            # Detect soft-404: server redirected to a known error page (e.g. nta.go.jp/error/404.htm)
            final_path = str(r.url).lower()
            if "/error/" in final_path or "404" in final_path.rsplit("/", 1)[-1]:
                return False, 404
            return True, r.status_code
    except Exception:  # noqa: BLE001
        return False, 0


def _verify_source_urls(state: PipelineState) -> list[FactCheckIssue]:
    """Check that every claim's source_urls are reachable. Dead links → high severity."""
    issues: list[FactCheckIssue] = []
    if state.script is None:
        return issues
    seen: dict[str, tuple[bool, int]] = {}
    for seg in state.script.segments:
        for c in seg.claims:
            for url in c.source_urls:
                if url not in seen:
                    seen[url] = _check_url_alive(url)
                alive, status = seen[url]
                if not alive:
                    issues.append(
                        FactCheckIssue(
                            segment_idx=seg.idx,
                            claim=c.text[:120],
                            severity="high",
                            reason=f"出典URLにアクセス不可 ({status or 'connection error'}): {url}",
                            suggested_fix="代替の一次ソースURLに差し替える",
                        )
                    )
    log.info("[factcheck] verified %d unique URLs, %d dead", len(seen), len(issues))
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

    issues = [FactCheckIssue(**i) for i in data.get("issues", [])]
    issues.extend(_verify_source_urls(state))

    report = FactCheckReport(
        issues=issues,
        verified_claim_count=data.get("verified_claim_count", 0),
        needs_human_review=data.get("needs_human_review", True) or bool(issues),
        primary_source_urls=sorted(
            {url for seg in script.segments for c in seg.claims for url in c.source_urls}
        ),
    )

    # Promote to Opus if there are high-severity issues.
    if any(i.severity == "high" for i in report.issues):
        log.info("[factcheck] high-severity issues found → re-run with opus tier")
        data2 = call_json(system=system, user=user, tier=config()["models"]["factcheck_hard"])
        if data2.get("issues") is not None:
            llm_issues = [FactCheckIssue(**i) for i in data2.get("issues", [])]
            # Keep dead-link issues from URL check (LLM can't verify network state)
            dead_link_issues = [i for i in report.issues if "アクセス不可" in i.reason]
            report.issues = llm_issues + dead_link_issues
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

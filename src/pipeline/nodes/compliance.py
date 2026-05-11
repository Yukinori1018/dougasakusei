"""Compliance node: four checks + AI disclosure checklist."""
from __future__ import annotations

from ..schemas import ComplianceFinding, ComplianceReport, PipelineState, SegmentSpeaker
from ..settings import config
from ..utils.io import write_json, write_text
from ..utils.llm import call_json
from ..utils.logging import get_logger

log = get_logger(__name__)


def _pattern_inauthentic(state: PipelineState) -> ComplianceFinding:
    """Heuristic: at least one substantive user-recorded segment is required."""
    if state.script is None:
        return ComplianceFinding(check="inauthentic", severity="warn", detail="台本未生成")
    user_sec = sum(s.duration_est_sec for s in state.script.user_segments())
    total = state.script.total_duration_est_sec or 1
    ratio = user_sec / total
    if user_sec < 60 or ratio < 0.1:
        return ComplianceFinding(
            check="inauthentic",
            severity="warn",
            detail=f"ユーザー録音セグメントの合計が短すぎます ({user_sec:.0f}s, 比率 {ratio:.0%})。"
            "YouTube の Inauthentic Content ポリシー対応のため、自分の声・体験談セグメントを増やすことを推奨。",
            suggestion="intro / 体験談 / conclusion のいずれかを USER に追加。",
        )
    return ComplianceFinding(
        check="inauthentic", severity="ok", detail=f"ユーザー音声 {user_sec:.0f}s ({ratio:.0%})"
    )


def _llm_review(state: PipelineState) -> list[ComplianceFinding]:
    if state.script is None:
        return []
    system = (
        "あなたは YouTube 動画の法務・コンプライアンス審査者です。出力は JSON のみ。"
        "下記の台本を、税理士法（特に非税理士の税務相談禁止）、金商法（断定的判断の提供）、"
        "著作権（無許諾引用・第三者素材）、医療/誇大表現の観点でレビューしてください。"
    )
    payload = [
        {"idx": s.idx, "speaker": s.speaker.value if hasattr(s.speaker, "value") else s.speaker, "text": s.text}
        for s in state.script.segments
    ]
    user = (
        "JSON keys: findings (list of {check, severity (ok|info|warn|block), detail, suggestion}). "
        "check は tax_law / copyright / financial_law / medical / inauthentic / other のいずれか。\n\n"
        f"segments: {payload}"
    )
    data = call_json(system=system, user=user, tier=config()["models"]["compliance"])
    return [ComplianceFinding(**f) for f in data.get("findings", [])]


def run(state: PipelineState) -> PipelineState:
    log.info("[compliance] running 4 checks")
    findings = _llm_review(state)
    findings.append(_pattern_inauthentic(state))

    if state.factcheck and state.factcheck.issues:
        high = [i for i in state.factcheck.issues if i.severity == "high"]
        if high:
            findings.append(
                ComplianceFinding(
                    check="hallucination",
                    severity="block",
                    detail=f"事実検証で {len(high)} 件の重大な未確認クレーム",
                    suggestion="出典追加または該当セグメント書き直し",
                )
            )

    blocking = any(f.severity == "block" for f in findings)
    checklist = [
        "YouTube Studio で『合成・改変メディア』の AI 使用開示にチェックを入れる",
        "概要欄末尾に税理士監修の有無 / 一般情報である旨を明記",
        "BGM のライセンスを再確認（library.json と一致しているか）",
        "B-roll 採用素材のクレジット要否を確認",
        "サムネに使用した数字・主張に出典があるか確認",
    ]

    report = ComplianceReport(
        findings=findings,
        blocking=blocking,
        ai_disclosure_required=True,
        checklist_for_studio=checklist,
    )

    pd = state.project_path()
    write_json(pd / "compliance" / "policy.json", report)
    write_text(pd / "compliance" / "final_report.md", _summary_md(report))
    state.compliance = report
    log.info("[compliance] %d findings (blocking=%s)", len(findings), blocking)
    return state


def _summary_md(r: ComplianceReport) -> str:
    out = ["# コンプライアンス最終レポート\n"]
    out.append(f"**ブロッキング状態**: {'⛔ あり' if r.blocking else '✅ なし'}\n")
    out.append("\n## チェック結果\n")
    for f in r.findings:
        icon = {"ok": "✅", "info": "ℹ️", "warn": "⚠️", "block": "⛔"}.get(f.severity, "•")
        out.append(f"- {icon} **{f.check}** ({f.severity}): {f.detail}")
        if f.suggestion:
            out.append(f"  - 推奨対応: {f.suggestion}")
    out.append("\n## YouTube Studio チェックリスト（投稿前必須）\n")
    for c in r.checklist_for_studio:
        out.append(f"- [ ] {c}")
    return "\n".join(out)

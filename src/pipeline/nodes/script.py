"""Script node: structured generation + oral-style rewrite."""
from __future__ import annotations

from ..schemas import PipelineState, Script, ScriptSegment, SegmentSpeaker
from ..settings import config
from ..utils.io import read_json, write_json, write_text
from ..utils.llm import call_json, call_llm
from ..utils.logging import get_logger

log = get_logger(__name__)


def _generate_structured(state: PipelineState) -> Script:
    cfg = config()
    target = cfg["long_form"]["target_duration_sec"]
    topic = state.topic
    brief = {}
    bp = state.project_path() / "research" / "brief.json"
    if bp.exists():
        brief = read_json(bp)

    system = (
        "あなたは事実ベースの YouTube 台本ライターです。出力は JSON のみ。"
        "セクション構成: intro(自己紹介・問題提起)→ body(3-5 つの論点)→ conclusion → cta。"
        "user(自分の声で録る重要発話) と ai(TTS で読む解説) を mix。"
        "重要な数値・体験談・結論・CTAは user に割り当てる。"
        "各 claim には source_urls を必ず付ける（一次ソース優先）。"
        "断定的判断の提供を避け、必要に応じて『個別判断は専門家に』の旨を含める。"
    )
    user = (
        f"テーマ: {topic.title_working if topic else state.config.topic}\n"
        f"視聴者: {topic.target_audience if topic else ''}\n"
        f"hook: {topic.hook if topic else ''}\n"
        f"keywords: {', '.join(topic.keywords) if topic else ''}\n"
        f"研究ブリーフ: {brief.get('brief', '')}\n"
        f"論点候補: {brief.get('key_points', [])}\n"
        f"目標尺(秒): {target}\n\n"
        "JSON keys: title, summary, segments[]。"
        "segments の各要素: idx (0始まり), speaker ('user'|'ai'), section, text, notes, "
        "visual_hint, duration_est_sec, claims (各 claim: text, source_urls[])"
    )
    data = call_json(system=system, user=user, tier=cfg["models"]["script"], max_tokens=6000)
    return Script.model_validate(data)


def _oralize(script: Script) -> Script:
    """Rewrite segments into oral style. Cheap-tier model."""
    cfg = config()
    for seg in script.segments:
        if not seg.text:
            continue
        system = (
            "次の文章を、YouTube ナレーションとして自然に読み上げられる口語に短く書き直してください。"
            "意味は変えず、長文は短文に区切る。出力は本文のみ、JSON や前置きなし。"
        )
        seg.text = call_llm(
            system=system, user=seg.text, tier=cfg["models"]["script_oralize"], max_tokens=600
        ).strip()
    return script


def run(state: PipelineState) -> PipelineState:
    log.info("[script] generating structured script")
    script = _generate_structured(state)

    # Normalise speaker enum + indices.
    for i, seg in enumerate(script.segments):
        seg.idx = i
        seg.speaker = SegmentSpeaker(seg.speaker) if isinstance(seg.speaker, str) else seg.speaker

    log.info("[script] oralizing %d segments", len(script.segments))
    script = _oralize(script)
    script.total_duration_est_sec = sum(s.duration_est_sec for s in script.segments)

    pd = state.project_path()
    write_json(pd / "script" / "script.json", script)
    write_text(pd / "script" / "script.md", _to_markdown(script))
    write_text(pd / "script" / "teleprompter.html", _to_teleprompter(script))

    state.script = script
    log.info(
        "[script] %d segments (user=%d, ai=%d), est %ds",
        len(script.segments),
        len(script.user_segments()),
        len(script.ai_segments()),
        int(script.total_duration_est_sec),
    )
    return state


def _to_markdown(s: Script) -> str:
    out = [f"# {s.title}\n\n_{s.summary}_\n"]
    for seg in s.segments:
        tag = "🎙️ USER（録音）" if seg.speaker == SegmentSpeaker.USER else "🤖 AI 音声"
        out.append(f"\n## [{seg.idx:02d}] {seg.section} — {tag} ({int(seg.duration_est_sec)}s)\n")
        out.append(seg.text + "\n")
        if seg.notes:
            out.append(f"\n> 📝 演出メモ: {seg.notes}\n")
        if seg.visual_hint:
            out.append(f"\n> 🎬 映像: {seg.visual_hint}\n")
        if seg.claims:
            out.append("\n出典:\n")
            for c in seg.claims:
                out.append(f"- {c.text} — {', '.join(c.source_urls) or '(要追加)'}\n")
    return "".join(out)


def _to_teleprompter(s: Script) -> str:
    rows = []
    for seg in s.segments:
        if seg.speaker != SegmentSpeaker.USER:
            continue
        rows.append(
            f'<div class="seg"><h3>セグメント {seg.idx:02d} ({seg.section}) — {int(seg.duration_est_sec)}秒</h3>'
            f"<p>{seg.text}</p>"
            + (f'<p class="note">📝 {seg.notes}</p>' if seg.notes else "")
            + "</div>"
        )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>録音用カンペ</title>"
        "<style>body{font-family:sans-serif;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.8}"
        ".seg{border-left:4px solid #4a9;padding:16px;margin:24px 0;background:#f8f8f8}"
        "h3{margin-top:0;color:#246}p{font-size:1.3em}.note{color:#a40;font-size:0.95em}</style></head>"
        f"<body><h1>{s.title}</h1>" + "".join(rows) + "</body></html>"
    )

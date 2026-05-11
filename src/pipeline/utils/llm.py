"""Tiered Anthropic Claude client with mock fallback and structured-output helpers."""
from __future__ import annotations

import json
import re
from typing import Any

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from ..settings import effective_mode, env
from .logging import get_logger

log = get_logger(__name__)

# Model IDs per https://docs.claude.com/en/docs/about-claude/models
TIER_TO_MODEL = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}


def _client() -> Anthropic:
    return Anthropic(api_key=env().ANTHROPIC_API_KEY)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def call_llm(
    *,
    system: str,
    user: str,
    tier: str = "sonnet",
    max_tokens: int = 4096,
    temperature: float = 0.4,
) -> str:
    if effective_mode() == "mock":
        return _mock_response(system, user)

    model = TIER_TO_MODEL.get(tier, TIER_TO_MODEL["sonnet"])
    resp = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")


def call_json(
    *,
    system: str,
    user: str,
    tier: str = "sonnet",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Force JSON output. The model is asked to wrap output in <json>...</json>."""
    wrapped_system = system + (
        "\n\n出力フォーマット: 必ず <json> と </json> で囲んだ valid JSON のみ出力すること。"
        "JSON 以外の前置きや後置きを書かない。"
    )
    raw = call_llm(system=wrapped_system, user=user, tier=tier, max_tokens=max_tokens, temperature=0.2)
    m = re.search(r"<json>(.*?)</json>", raw, re.S)
    payload = m.group(1) if m else raw
    try:
        return json.loads(payload)
    except json.JSONDecodeError as e:
        log.warning("JSON parse failed (%s). raw=%s", e, raw[:300])
        return {}


# -----------------------------------------------------------------------------
# Mock dispatch — keyed on system prompt so the whole pipeline can run without
# real API access for smoke-testing.
# -----------------------------------------------------------------------------

def _mock_response(system: str, user: str) -> str:
    if "口語" in system or "読み上げ" in system:
        return user  # oralize passthrough
    if "台本ライター" in system:
        return _MOCK_SCRIPT
    if "ファクトチェッカー" in system:
        return '<json>{"issues": [], "verified_claim_count": 5, "needs_human_review": true}</json>'
    if "コンプライアンス" in system:
        return _MOCK_COMPLIANCE
    if "リサーチャー" in system:
        return _MOCK_RESEARCH
    if "切り出し候補" in system or "ショート" in system:
        return _MOCK_SHORTS
    if "サムネ" in system:
        return '<json>{"copies": ["年間40万損", "Before→After", "知らないと損"]}</json>'
    if "SEO" in system or "タイトル候補" in system:
        return _MOCK_METADATA
    if "選曲" in system or "BGM" in system:
        return '<json>{"id": "calm_corporate_01"}</json>'
    if "企画者" in system:
        return _MOCK_TOPIC
    return "<json>{}</json>"


_MOCK_TOPIC = """<json>{
  "slug": "invoice-keiakasochi-2026",
  "title_working": "【2026年最新】インボイス経過措置がもうすぐ終了。中小事業者が今やるべき5つの対策",
  "hook": "見落とすと年間数十万円の損失。経過措置の終わりを正しく理解する。",
  "target_audience": "年商1000万〜3億の中小企業オーナー / 個人事業主",
  "keywords": ["インボイス", "経過措置", "簡易課税", "免税事業者", "2026"],
  "rationale": "経過措置の終了時期が近く検索需要が再上昇している。"
}</json>"""

_MOCK_RESEARCH = """<json>{
  "brief": "インボイス制度の経過措置（仕入税額控除の段階的縮小）は2026年9月末で第二段階が終了する見込み。中小事業者にとっては実質的な税負担増となる局面で、簡易課税の選択や免税事業者との取引見直し、AI による経理自動化が論点。",
  "key_points": [
    "経過措置の3段階構造とそれぞれの控除率",
    "簡易課税制度の選択判断基準",
    "免税事業者との取引継続/見直しの実務",
    "AI を使った仕訳自動化の具体例",
    "2026年9月期限に向けた逆算スケジュール"
  ],
  "primary_source_urls": [
    "https://www.nta.go.jp/taxes/shiraberu/zeimokubetsu/shohi/keigenzeiritsu/invoice.htm",
    "https://www.chusho.meti.go.jp/zaimu/zeisei/invoice.html"
  ]
}</json>"""

_MOCK_SCRIPT = """<json>{
  "title": "【2026年最新】インボイス経過措置の終了で中小企業が今やるべき5つの対策",
  "summary": "インボイス経過措置の終了に伴う実務的な対策と、AIツールで負担を減らす方法を解説。",
  "segments": [
    {"idx": 0, "speaker": "user", "section": "intro", "text": "こんにちは。今日はインボイス経過措置の終了について話します。", "notes": "落ち着いた挨拶", "visual_hint": "オープニングロゴ", "duration_est_sec": 12, "claims": []},
    {"idx": 1, "speaker": "ai", "section": "body", "text": "まずインボイス経過措置とは、2023年10月にインボイス制度が始まった際に設けられた、免税事業者からの仕入れについて段階的に仕入税額控除を縮小していく仕組みです。", "notes": "", "visual_hint": "制度フロー図表", "duration_est_sec": 25, "claims": [{"text": "2023年10月にインボイス制度が開始", "source_urls": ["https://www.nta.go.jp/taxes/shiraberu/zeimokubetsu/shohi/keigenzeiritsu/invoice.htm"]}]},
    {"idx": 2, "speaker": "ai", "section": "body", "text": "経過措置は3年ごとに段階的に縮小され、最終的に完全に廃止されます。", "notes": "", "visual_hint": "棒グラフ", "duration_est_sec": 20, "claims": []},
    {"idx": 3, "speaker": "user", "section": "body", "text": "私自身、この経過措置の対応で実際に困った経験があります。具体的にはこういうケースで、こう乗り切りました。", "notes": "落ち着いた語り口で。具体例を入れる。", "visual_hint": "実体験スクショ", "duration_est_sec": 60, "claims": []},
    {"idx": 4, "speaker": "ai", "section": "body", "text": "次に、中小事業者が今やるべき5つの対策を順に解説します。1つ目は簡易課税制度の検討、2つ目は免税事業者との取引見直し…", "notes": "", "visual_hint": "リスト表示", "duration_est_sec": 120, "claims": []},
    {"idx": 5, "speaker": "ai", "section": "body", "text": "ここで実際に私が使っているAIツールでの仕訳自動化のデモをご覧ください。", "notes": "", "visual_hint": "AIツール画面録画", "duration_est_sec": 90, "claims": []},
    {"idx": 6, "speaker": "user", "section": "conclusion", "text": "ここまで5つの対策を解説しました。一番大事なのは早めに着手することです。", "notes": "結論は強めに。", "visual_hint": "まとめスライド", "duration_est_sec": 40, "claims": []},
    {"idx": 7, "speaker": "user", "section": "cta", "text": "参考になったらチャンネル登録お願いします。次回もお楽しみに。", "notes": "", "visual_hint": "登録ボタン", "duration_est_sec": 15, "claims": []}
  ]
}</json>"""

_MOCK_METADATA = """<json>{
  "title_candidates": [
    "【2026年最新】インボイス経過措置の終了で何が変わる？中小企業が今やる5つの対策",
    "知らないと損するインボイス経過措置の終わり｜AIで楽になる経理術",
    "インボイス経過措置 完全ガイド 2026｜免税事業者の最適解",
    "【保存版】経過措置終了で年間40万円の差｜中小企業の生存戦略",
    "AIで仕訳10倍速｜インボイス経過措置の終わりに備える"
  ],
  "chosen_title": "【2026年最新】インボイス経過措置の終了で何が変わる？中小企業が今やる5つの対策",
  "description": "本動画では2026年最新の制度変更点と、AIを使った経理の自動化方法を解説します。\\n\\n00:00 イントロ\\n00:30 経過措置の仕組み\\n02:00 5つの対策\\n08:00 AIツール実演\\n\\n参考: 国税庁 https://www.nta.go.jp/",
  "tags": ["インボイス", "経過措置", "簡易課税", "中小企業", "税金", "AI経理", "確定申告", "個人事業主", "免税事業者", "2026", "節税", "補助金", "freee", "マネーフォワード", "ChatGPT"],
  "seo_competition_score": 0.45
}</json>"""

_MOCK_COMPLIANCE = """<json>{
  "findings": [
    {"check": "tax_law", "severity": "info", "detail": "断定的表現なし。免責文言が必要。", "suggestion": "概要欄に税理士監修の有無を明記"},
    {"check": "copyright", "severity": "ok", "detail": "第三者素材の引用は確認できず。", "suggestion": ""}
  ],
  "blocking": false,
  "ai_disclosure_required": true
}</json>"""

_MOCK_SHORTS = """<json>{
  "candidates": [
    {"idx": 1, "start_sec": 90, "end_sec": 145, "hook": "経過措置の終了で年商1000万の事業者は実質40万の負担増", "rationale": "数字インパクト"},
    {"idx": 2, "start_sec": 250, "end_sec": 300, "hook": "簡易課税を選ぶべき3つの条件", "rationale": "ハウツーまとめ"},
    {"idx": 3, "start_sec": 320, "end_sec": 375, "hook": "AIで仕訳が10倍速になった具体例", "rationale": "実演ショット"},
    {"idx": 4, "start_sec": 410, "end_sec": 460, "hook": "免税事業者との取引、続ける？切る？", "rationale": "問いかけ系"},
    {"idx": 5, "start_sec": 520, "end_sec": 575, "hook": "結論: 動くなら今月中", "rationale": "結論系"}
  ]
}</json>"""

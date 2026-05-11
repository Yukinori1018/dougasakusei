"""Trend collection: pull from public RSS feeds and let an LLM rank candidates.

Strategy:
1. Try RSS feeds (best effort; Japanese govt feeds are unreliable).
2. If RSS yields nothing, ask Claude to brainstorm timely topics for our niche
   using its knowledge of current Japanese SMB / tax / subsidy events.

The LLM ranker is the real intelligence; RSS is a tiebreaker / freshness signal.
"""
from __future__ import annotations

import datetime as _dt
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from .llm import call_json
from .logging import get_logger

log = get_logger(__name__)


# Best-effort RSS sources. These URLs change occasionally; failures are tolerated
# and the LLM brainstorm fallback kicks in.
_RSS_SOURCES = [
    "https://www.meti.go.jp/main/rss/press.rdf",        # 経済産業省 プレス
    "https://www.j-net21.smrj.go.jp/rss/news.xml",      # J-Net21
    "https://www.zaikei.co.jp/rss/sougou.xml",          # 財経新聞 総合
    "https://www3.nhk.or.jp/rss/news/cat5.xml",         # NHK 経済
]


@dataclass
class TrendItem:
    title: str
    link: str
    source: str
    summary: str = ""


def _fetch_rss(url: str) -> list[TrendItem]:
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as c:
            r = c.get(url, headers={"User-Agent": "dougasakusei-trends/0.1"})
            r.raise_for_status()
            body = r.text
    except Exception as e:  # noqa: BLE001
        log.warning("trend fetch failed: %s (%s)", url, e)
        return []
    return _parse_feed(body, source=url)


def _parse_feed(body: str, source: str) -> list[TrendItem]:
    """Best-effort parser handling RSS 2.0, RSS 1.0 (RDF), and Atom."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        log.warning("RSS parse error from %s: %s", source, e)
        return []

    items: list[TrendItem] = []

    def _strip_ns(tag: str) -> str:
        return tag.split("}", 1)[1] if "}" in tag else tag

    for el in root.iter():
        if _strip_ns(el.tag) not in ("item", "entry"):
            continue
        title = ""
        link = ""
        summary = ""
        for child in el:
            tag = _strip_ns(child.tag)
            text = (child.text or "").strip()
            if tag == "title":
                title = text
            elif tag == "link":
                link = child.attrib.get("href") or text
            elif tag in ("description", "summary"):
                summary = re.sub(r"<[^>]+>", "", text)[:300]
        if title:
            items.append(TrendItem(title=title, link=link, source=source, summary=summary))

    return items[:15]  # cap per feed


def _brainstorm_fallback() -> list[TrendItem]:
    """When RSS yields nothing, ask Claude to enumerate timely SMB/tax topics."""
    today = _dt.date.today().isoformat()
    system = (
        "あなたは中小企業オーナー向け『AI × 税務・補助金』YouTube チャンネルの編集者です。"
        f"今日は {today}。直近3ヶ月以内に検索需要が高まる、または期限が迫っている日本の中小企業向け"
        "税務・補助金・制度変更トピックを 8 件挙げてください。出力は JSON のみ。"
    )
    user = (
        "JSON keys: items (list of {title, summary, link})。"
        "title は YouTube サムネ向けの 30 文字以内、summary は 80 文字以内、"
        "link は出典となる公式サイト URL（nta.go.jp / chusho.meti.go.jp / meti.go.jp 等）。"
    )
    data = call_json(system=system, user=user, tier="sonnet")
    return [
        TrendItem(
            title=it.get("title", ""),
            link=it.get("link", ""),
            source="llm-brainstorm",
            summary=it.get("summary", ""),
        )
        for it in data.get("items", [])
        if it.get("title")
    ]


def collect_trends() -> list[TrendItem]:
    items: list[TrendItem] = []
    for url in _RSS_SOURCES:
        items.extend(_fetch_rss(url))
    log.info("[trends] collected %d items from %d RSS feeds", len(items), len(_RSS_SOURCES))
    if not items:
        log.info("[trends] RSS empty — falling back to LLM brainstorm")
        items = _brainstorm_fallback()
        log.info("[trends] brainstorm produced %d items", len(items))
    return items


def rank_topics(items: list[TrendItem], n: int = 3) -> list[dict]:
    """Ask Claude to pick the top N items for our SMB-tax-AI channel."""
    if not items:
        return []
    payload = [{"title": i.title, "summary": i.summary, "link": i.link} for i in items]
    system = (
        "あなたは中小企業オーナー向け『AI × 税務・補助金』YouTube チャンネルの編集長です。"
        "下記のニュース見出し群から、検索需要が見込めて視聴者の意思決定に直結するトピックを"
        f"{n} 件選び、動画化用に整形してください。出力は JSON のみ。"
    )
    user = (
        f"候補ニュース:\n{payload}\n\n"
        "JSON keys: picks (list of {topic_phrase, hook, why_now, suggested_keywords, "
        "source_url})。topic_phrase は『〜について解説』ではなく『〇〇が△△に変わる、今やる5つの対策』"
        "のように具体的な行動を促す表現で。"
    )
    data = call_json(system=system, user=user, tier="sonnet")
    return data.get("picks", [])

"""Trend collection: pull from public RSS feeds and let an LLM rank candidates.

We avoid the unofficial Google Trends scrapers (pytrends is fragile and
intermittently blocks). Instead we pull RSS feeds that are stable and
freely accessible, then ask Claude to dedupe and rank for our channel niche.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from .llm import call_json
from .logging import get_logger

log = get_logger(__name__)


# Stable RSS sources that cover Japanese SMB / tax / subsidy / AI topics.
# Keep this list short — the LLM ranker is the real intelligence.
_RSS_SOURCES = [
    # 国税庁 新着情報（JSON 風だが RSS 互換ではない場合があるため除外）
    "https://www.chusho.meti.go.jp/koukai/rss/index.rdf",  # 中小企業庁
    "https://www.meti.go.jp/rss/press.rdf",  # 経済産業省 プレス
    "https://www.j-net21.smrj.go.jp/snews/rss/news.xml",  # J-Net21
    "https://www.mof.go.jp/rss/news.xml",  # 財務省
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


def collect_trends() -> list[TrendItem]:
    items: list[TrendItem] = []
    for url in _RSS_SOURCES:
        items.extend(_fetch_rss(url))
    log.info("[trends] collected %d items from %d feeds", len(items), len(_RSS_SOURCES))
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

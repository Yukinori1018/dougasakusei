"""Metadata node: title candidates, description, tags + light SEO competition score."""
from __future__ import annotations

import httpx

from ..schemas import Metadata, PipelineState
from ..settings import config, env
from ..utils.io import write_json, write_text
from ..utils.llm import call_json
from ..utils.logging import get_logger

log = get_logger(__name__)


def _seo_score(query: str) -> float:
    key = env().YOUTUBE_DATA_API_KEY
    if not key:
        return 0.5
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={"part": "snippet", "q": query, "type": "video", "maxResults": 5, "key": key},
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            return min(1.0, len(items) / 5.0)
    except Exception as e:  # noqa: BLE001
        log.warning("YouTube SEO check failed: %s", e)
        return 0.5


def run(state: PipelineState) -> PipelineState:
    log.info("[metadata] generating titles / description / tags")
    cfg = config()
    topic = state.topic
    summary = state.script.summary if state.script else ""
    disclaimer = cfg["channel"]["disclaimer"]

    system = (
        "あなたは YouTube SEO ライターです。出力は JSON のみ。"
        "視聴者の検索意図に応えるタイトル候補を 10 案、概要欄、タグ 15 個を生成。"
        "タイトル: 35-45 文字、【】に年や数字、ベネフィットを必ず含む。"
    )
    user = (
        f"テーマ: {topic.title_working if topic else state.config.topic}\n"
        f"要約: {summary}\n"
        f"keywords: {', '.join(topic.keywords) if topic else ''}\n"
        "JSON keys: title_candidates (list[str]), chosen_title (str), description (str), tags (list[str])"
    )
    data = call_json(system=system, user=user, tier=cfg["models"]["metadata"])

    candidates = data.get("title_candidates", [])
    chosen = data.get("chosen_title", candidates[0] if candidates else state.config.topic)
    description = data.get("description", "")
    if disclaimer not in description:
        description = description.rstrip() + "\n\n---\n" + disclaimer
    tags = data.get("tags", [])

    score = _seo_score(chosen) if chosen else 0.5

    md = Metadata(
        title_candidates=list(candidates),
        chosen_title=chosen,
        description=description,
        tags=list(tags),
        seo_competition_score=score,
        notes=f"YouTube Data API 検索ヒット率ベースの簡易スコア (0..1, 高いほど競合多)",
    )

    pd = state.project_path()
    write_json(pd / "metadata" / "metadata.json", md)
    write_text(pd / "metadata" / "description.md", description)
    write_text(pd / "metadata" / "tags.txt", "\n".join(tags))
    write_text(
        pd / "metadata" / "seo_report.md",
        f"# SEO レポート\n\n- 選定タイトル: {chosen}\n- 競合度スコア: {score:.2f}\n"
        f"- 候補数: {len(candidates)}\n- タグ数: {len(tags)}\n",
    )
    state.metadata = md
    log.info("[metadata] chosen='%s' (score=%.2f)", chosen, score)
    return state

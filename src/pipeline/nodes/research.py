"""Research node: collect primary-source material for the chosen topic."""
from __future__ import annotations

from pathlib import Path

import httpx

from ..schemas import PipelineState, Source
from ..settings import config, effective_mode
from ..utils.io import write_json
from ..utils.llm import call_json
from ..utils.logging import get_logger
from ..utils.urlcheck import check_url_alive

log = get_logger(__name__)


def _fetch_safely(url: str) -> str:
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as c:
            r = c.get(url, headers={"User-Agent": "dougasakusei-research/0.1"})
            r.raise_for_status()
            return r.text[:20000]
    except Exception as e:  # noqa: BLE001 — best-effort
        log.warning("fetch failed: %s (%s)", url, e)
        return ""


def run(state: PipelineState) -> PipelineState:
    log.info("[research] gathering primary sources")
    pd = state.project_path()
    raw_dir = pd / "research" / "raw"

    # In mock mode we skip network. In auto mode we pull each whitelisted domain's
    # home page as a seed; richer crawling is left to downstream LLM web_search.
    if effective_mode() == "auto":
        for src in state.sources:
            body = _fetch_safely(src.url)
            if body:
                (raw_dir / (src.domain or "src").replace("/", "_")).with_suffix(".html").write_text(
                    body, encoding="utf-8"
                )
                src.snippet = body[:500]

    # Ask the LLM to draft a research brief grounded in the topic. The LLM is
    # also responsible for naming additional URLs it would want to verify against.
    topic = state.topic
    system = (
        "あなたはリサーチャーです。出力は JSON のみ。"
        "対象動画のための事実ベースの論点と、確認すべき一次ソース URL リストを返してください。"
    )
    user = (
        f"動画タイトル案: {topic.title_working if topic else ''}\n"
        f"hook: {topic.hook if topic else ''}\n"
        f"keywords: {', '.join(topic.keywords) if topic else ''}\n\n"
        "JSON keys: brief (string, 400字程度), key_points (list of 5-8 string), "
        "primary_source_urls (list of full URLs from nta.go.jp, chusho.meti.go.jp, mirasapo-plus.go.jp, e-gov.go.jp, etc.)"
    )
    data = call_json(system=system, user=user, tier=config()["models"]["research"])

    brief = {
        "brief": data.get("brief", ""),
        "key_points": data.get("key_points", []),
    }
    proposed = [u for u in data.get("primary_source_urls", []) if isinstance(u, str)]
    dead: list[str] = []
    for url in proposed:
        if effective_mode() == "auto":
            alive, status = check_url_alive(url)
            if not alive:
                dead.append(f"{url} (status={status or 'conn-err'})")
                continue
        domain = httpx.URL(url).host if url.startswith("http") else ""
        state.sources.append(Source(url=url, domain=domain, is_primary=True))
    if dead:
        log.warning("[research] dropped %d dead LLM-suggested URLs: %s", len(dead), dead)
        brief["dropped_urls"] = dead

    write_json(pd / "research" / "brief.json", brief)
    write_json(pd / "research" / "sources.json", state.sources)
    log.info("[research] %d sources collected", len(state.sources))
    return state

"""Topic selection: either use a user-supplied topic or auto-pick from trends."""
from __future__ import annotations

import re

from ..schemas import PipelineState, Source, Topic
from ..settings import config
from ..utils.io import write_json
from ..utils.llm import call_json
from ..utils.logging import get_logger
from ..utils.paths import new_project_dir

log = get_logger(__name__)


def _flatten_to_str(v) -> str:
    """Claude sometimes returns rich structures where we expect a string. Flatten safely."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return " / ".join(_flatten_to_str(x) for x in v.values() if x)
    if isinstance(v, list):
        return " / ".join(_flatten_to_str(x) for x in v if x)
    return str(v)


def _coerce_topic_data(data: dict) -> dict:
    """Coerce LLM output into shapes the Topic schema accepts."""
    out = dict(data)
    for str_field in ("slug", "title_working", "hook", "target_audience", "rationale"):
        if str_field in out:
            out[str_field] = _flatten_to_str(out[str_field])
    if "keywords" in out and not isinstance(out["keywords"], list):
        out["keywords"] = [_flatten_to_str(out["keywords"])]
    return out


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9一-龯ぁ-んァ-ヶー]+", "-", s)
    return s.strip("-")[:60].lower() or "video"


def run(state: PipelineState) -> PipelineState:
    log.info("[topic] selecting topic for: %s", state.config.topic)

    system = (
        "あなたは中小企業オーナー向けの『AI × 税務・補助金』専門 YouTube チャンネルの企画者です。"
        "視聴者は年商1000万〜3億円の経営者・個人事業主。動画は税理士監修前提の一次情報重視。"
        "出力は schema に厳密に従ってください。"
    )
    user = (
        f"トピック: {state.config.topic}\n"
        f"シード語: {', '.join(state.config.seed_keywords) or '(なし)'}\n\n"
        "次のフィールドを返してください: slug (英数+ハイフン), title_working, hook, "
        "target_audience, keywords (5-8), rationale"
    )

    data = call_json(system=system, user=user, tier=config()["models"]["research"])
    if not data:
        data = {
            "slug": _slugify(state.config.topic),
            "title_working": state.config.topic,
            "hook": "",
            "target_audience": "中小企業オーナー",
            "keywords": state.config.seed_keywords,
            "rationale": "ユーザー指定",
        }

    data = _coerce_topic_data(data)
    topic = Topic(**{k: v for k, v in data.items() if k in Topic.model_fields})
    topic.slug = _slugify(topic.slug or state.config.topic)

    # Provision the on-disk project directory now that we have a slug.
    pd = new_project_dir(topic.slug)
    state.project_dir = str(pd)
    state.topic = topic

    write_json(pd / "config.json", state.config)
    write_json(pd / "research" / "topic.json", topic)

    # Seed with primary-source domains as research starting points.
    primary_domains = config()["research"]["primary_sources"]
    state.sources = [
        Source(url=f"https://{d}/", domain=d, is_primary=True) for d in primary_domains
    ]
    log.info("[topic] slug=%s, project=%s", topic.slug, pd)
    return state

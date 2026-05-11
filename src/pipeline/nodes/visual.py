"""Visual node: B-roll candidate collection + chart generation + thumbnails."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

from ..schemas import PipelineState, ThumbnailCandidate, VisualAsset
from ..settings import config, effective_mode, env
from ..utils.io import write_json, write_text
from ..utils.logging import get_logger
from ..utils.llm import call_json

log = get_logger(__name__)


def _pexels_search(query: str, per_page: int) -> list[dict]:
    key = env().PEXELS_API_KEY
    if not key:
        return []
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": key},
                params={"query": query, "per_page": per_page, "orientation": "landscape"},
            )
            r.raise_for_status()
            return r.json().get("videos", [])
    except Exception as e:  # noqa: BLE001
        log.warning("Pexels search failed: %s", e)
        return []


def _pixabay_search(query: str, per_page: int) -> list[dict]:
    key = env().PIXABAY_API_KEY
    if not key:
        return []
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(
                "https://pixabay.com/api/videos/",
                params={"key": key, "q": query, "per_page": per_page, "safesearch": "true"},
            )
            r.raise_for_status()
            return r.json().get("hits", [])
    except Exception as e:  # noqa: BLE001
        log.warning("Pixabay search failed: %s", e)
        return []


def _broll_candidates(state: PipelineState) -> list[VisualAsset]:
    cfg = config()
    per = cfg["broll"]["candidates_per_query"]
    pd = state.project_path()
    out: list[VisualAsset] = []
    if state.script is None:
        return out

    queries = []
    for seg in state.script.segments:
        if seg.visual_hint and not any(k in seg.visual_hint for k in ("画面録画", "図", "リスト", "ロゴ")):
            queries.append((seg.idx, seg.visual_hint))

    if effective_mode() == "mock" or (not env().PEXELS_API_KEY and not env().PIXABAY_API_KEY):
        # Generate placeholder JSON only — human will fill in later.
        for idx, q in queries:
            out.append(
                VisualAsset(kind="placeholder", path="", source="manual", query=q, segment_idx=idx)
            )
        return out

    for idx, q in queries:
        candidates = _pexels_search(q, per) or _pixabay_search(q, per)
        for cand in candidates[:per]:
            video_files = cand.get("video_files") or cand.get("videos", {}).get("medium", {})
            url = ""
            if isinstance(video_files, list) and video_files:
                url = video_files[0].get("link", "")
            elif isinstance(video_files, dict):
                url = video_files.get("url", "")
            if not url:
                continue
            out.append(
                VisualAsset(
                    kind="broll",
                    path=url,
                    source="pexels" if "pexels" in url else "pixabay",
                    license="free-with-attribution",
                    segment_idx=idx,
                    query=q,
                )
            )

    # Write the candidate gallery for human selection.
    gallery_html = "<html><body><h1>B-roll candidates — accept by editing accepted=true</h1>"
    for v in out:
        gallery_html += f"<h3>seg {v.segment_idx} — {v.query} ({v.source})</h3>"
        gallery_html += f'<video src="{v.path}" controls width=400></video><br>'
    gallery_html += "</body></html>"
    write_text(pd / "visuals" / "broll" / "gallery.html", gallery_html)
    return out


def _generate_thumbnails(state: PipelineState) -> list[ThumbnailCandidate]:
    cfg = config()
    pd = state.project_path()
    strategies = [
        ("A", "数字インパクト訴求"),
        ("B", "Before/After対比"),
        ("C", "疑問形・好奇心フック"),
    ]
    candidates: list[ThumbnailCandidate] = []
    title = state.topic.title_working if state.topic else state.config.topic

    # Ask LLM for short overlay copy per strategy.
    system = "サムネ用の短いキャッチコピーを3案、JSON で返してください。各案 12 文字以内。"
    data = call_json(system=system, user=f"動画タイトル: {title}", tier=cfg["models"]["metadata"])
    copies = data.get("copies") or data.get("captions") or [title[:12]] * 3

    for (variant, strategy), copy in zip(strategies, list(copies) + [title] * 3, strict=False):
        path = pd / "visuals" / "thumbnails" / f"thumb_{variant}.png"
        _render_thumbnail_placeholder(path, str(copy), variant)
        candidates.append(
            ThumbnailCandidate(
                variant=variant,
                strategy=strategy,
                path=str(path.relative_to(pd)),
                title_overlay=str(copy),
            )
        )
    return candidates


def _render_thumbnail_placeholder(path: Path, copy: str, variant: str) -> None:
    """Render a minimal PNG without external image generation, using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return
    w, h = 1280, 720
    bg = {"A": (220, 50, 70), "B": (40, 90, 200), "C": (70, 160, 90)}[variant]
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 96)
    except OSError:
        font = ImageFont.load_default()
    d.text((60, h // 2 - 60), copy, fill=(255, 255, 255), font=font)
    d.text((60, 40), f"VARIANT {variant}", fill=(255, 255, 0), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def run(state: PipelineState) -> PipelineState:
    log.info("[visual] collecting B-roll candidates")
    visuals = _broll_candidates(state)
    log.info("[visual] generating thumbnails")
    thumbs = _generate_thumbnails(state)

    pd = state.project_path()
    write_json(pd / "visuals" / "broll" / "candidates.json", visuals)
    write_json(pd / "visuals" / "thumbnails" / "candidates.json", thumbs)

    state.visuals = visuals
    state.thumbnails = thumbs
    log.info("[visual] %d broll candidates, %d thumbnails", len(visuals), len(thumbs))
    return state

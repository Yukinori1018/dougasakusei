"""Chart generation node: matplotlib-based templates for common visual_hints.

Detects keywords like 'タイムライン', '比較', '試算', 'スケジュール', '推移' in each
segment's visual_hint and renders a PNG into visuals/charts/. The LLM picks
template + data; matplotlib renders. Manim-grade animation is left for a future
upgrade (this stays cheap and ffmpeg-friendly).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..schemas import PipelineState, VisualAsset
from ..settings import config
from ..utils.io import write_json
from ..utils.llm import call_json
from ..utils.logging import get_logger

log = get_logger(__name__)


# Map keywords in visual_hint → template name. First match wins.
_TEMPLATE_KEYWORDS: list[tuple[str, str]] = [
    ("タイムライン", "timeline"),
    ("スケジュール", "timeline"),
    ("ロードマップ", "timeline"),
    ("比較", "comparison_bar"),
    ("対比", "comparison_bar"),
    ("Before/After", "comparison_bar"),
    ("試算", "calculation_table"),
    ("計算", "calculation_table"),
    ("シミュレーション", "calculation_table"),
    ("推移", "trend_line"),
    ("グラフ", "trend_line"),
]


def _pick_template(visual_hint: str) -> str | None:
    for kw, name in _TEMPLATE_KEYWORDS:
        if kw in visual_hint:
            return name
    return None


def _ask_llm_for_chart_data(template: str, visual_hint: str, segment_text: str) -> dict[str, Any]:
    schema_hint = {
        "timeline": (
            "JSON keys: title (string), milestones (list of {date: string, label: string}). "
            "milestones は3〜6個。"
        ),
        "comparison_bar": (
            "JSON keys: title, x_labels (list of 2-4 string), series "
            "(list of {name: string, values: list of number}). "
            "values の長さは x_labels と一致。"
        ),
        "calculation_table": (
            "JSON keys: title, headers (list of 2-4 string), rows (list of list of string)。"
            "rows は3〜6行、数値表現は『〜万円』『〜%』等の表記をそのまま。"
        ),
        "trend_line": (
            "JSON keys: title, x_labels (list of 4-8 string), series "
            "(list of {name: string, values: list of number})."
        ),
    }[template]

    system = (
        "あなたは台本から動画用の図表データを抽出するアシスタントです。出力は JSON のみ。"
        "本文に出てくる具体的な数値・期日・名称を忠実に拾うこと。創作しない。"
    )
    user = (
        f"テンプレート: {template}\n"
        f"映像指示: {visual_hint}\n"
        f"本文: {segment_text}\n\n"
        f"スキーマ: {schema_hint}"
    )
    return call_json(system=system, user=user, tier=config()["models"]["metadata"])


def _setup_jp_font() -> None:
    """Try to use a Japanese-capable font if available; otherwise fall back to default."""
    candidates = [
        "Hiragino Sans",
        "Hiragino Maru Gothic Pro",
        "Yu Gothic",
        "Noto Sans CJK JP",
        "IPAexGothic",
        "TakaoGothic",
        "DejaVu Sans",
    ]
    for f in candidates:
        try:
            plt.rcParams["font.family"] = f
            return
        except Exception:  # noqa: BLE001
            continue


def _render_timeline(data: dict, out_path: Path) -> None:
    milestones = data.get("milestones", [])
    if not milestones:
        return
    fig, ax = plt.subplots(figsize=(14, 4))
    xs = list(range(len(milestones)))
    ax.plot(xs, [0] * len(xs), "o-", color="#246", linewidth=2, markersize=12)
    for x, m in zip(xs, milestones):
        ax.annotate(
            m.get("label", ""),
            xy=(x, 0),
            xytext=(0, 30 if x % 2 == 0 else -40),
            textcoords="offset points",
            ha="center",
            fontsize=11,
        )
        ax.annotate(
            m.get("date", ""),
            xy=(x, 0),
            xytext=(0, -20 if x % 2 == 0 else 20),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color="#a40",
        )
    ax.set_ylim(-1, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)
    ax.set_title(data.get("title", ""), fontsize=14, pad=20)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_comparison_bar(data: dict, out_path: Path) -> None:
    series = data.get("series", [])
    x_labels = data.get("x_labels", [])
    if not series or not x_labels:
        return
    fig, ax = plt.subplots(figsize=(10, 6))
    n = len(series)
    width = 0.8 / max(n, 1)
    for i, s in enumerate(series):
        vals = s.get("values", [])[: len(x_labels)]
        offsets = [j + (i - n / 2 + 0.5) * width for j in range(len(x_labels))]
        ax.bar(offsets, vals, width, label=s.get("name", ""))
    ax.set_xticks(range(len(x_labels)))
    ax.set_xticklabels(x_labels)
    ax.set_title(data.get("title", ""), fontsize=14)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_calculation_table(data: dict, out_path: Path) -> None:
    headers = data.get("headers", [])
    rows = data.get("rows", [])
    if not headers or not rows:
        return
    fig, ax = plt.subplots(figsize=(10, 0.6 + 0.5 * len(rows)))
    ax.axis("off")
    table = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.8)
    for j in range(len(headers)):
        table[(0, j)].set_facecolor("#246")
        table[(0, j)].set_text_props(color="white", weight="bold")
    ax.set_title(data.get("title", ""), fontsize=14, pad=10)
    fig.savefig(out_path, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _render_trend_line(data: dict, out_path: Path) -> None:
    series = data.get("series", [])
    x_labels = data.get("x_labels", [])
    if not series or not x_labels:
        return
    fig, ax = plt.subplots(figsize=(10, 6))
    for s in series:
        ax.plot(x_labels, s.get("values", [])[: len(x_labels)], marker="o", label=s.get("name", ""))
    ax.set_title(data.get("title", ""), fontsize=14)
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)


_RENDERERS = {
    "timeline": _render_timeline,
    "comparison_bar": _render_comparison_bar,
    "calculation_table": _render_calculation_table,
    "trend_line": _render_trend_line,
}


def run(state: PipelineState) -> PipelineState:
    if state.script is None:
        return state
    _setup_jp_font()

    pd = state.project_path()
    charts_dir = pd / "visuals" / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_index: list[dict] = []
    new_visuals: list[VisualAsset] = []

    for seg in state.script.segments:
        template = _pick_template(seg.visual_hint or "")
        if not template:
            continue
        try:
            data = _ask_llm_for_chart_data(template, seg.visual_hint, seg.text)
            if not data:
                continue
            out = charts_dir / f"seg_{seg.idx:03d}_{template}.png"
            _RENDERERS[template](data, out)
            if not out.exists():
                continue
            chart_index.append(
                {
                    "segment_idx": seg.idx,
                    "template": template,
                    "path": str(out.relative_to(pd)),
                    "title": data.get("title", ""),
                }
            )
            new_visuals.append(
                VisualAsset(
                    kind="chart",
                    path=str(out.relative_to(pd)),
                    source="matplotlib",
                    segment_idx=seg.idx,
                    query=seg.visual_hint,
                    accepted=True,
                )
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[charts] seg %d (%s) failed: %s", seg.idx, template, e)

    write_json(pd / "visuals" / "charts" / "index.json", chart_index)
    state.visuals.extend(new_visuals)
    log.info("[charts] rendered %d charts", len(chart_index))
    return state

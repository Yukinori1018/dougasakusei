"""Typer CLI entry point."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .graph import build_graph
from .schemas import Format, Mode, PipelineState, ProjectConfig
from .settings import effective_mode

app = typer.Typer(add_completion=False, help="半自動 YouTube 動画生成パイプライン")
console = Console()


def _run(topic: str, fmt: Format, keywords: list[str]) -> PipelineState:
    mode = Mode(effective_mode())
    console.print(Panel.fit(f"[bold]パイプライン開始[/bold]\nmode={mode.value} / format={fmt.value}\ntopic={topic}"))

    state = PipelineState(
        config=ProjectConfig(slug="tbd", topic=topic, format=fmt, seed_keywords=keywords),
        project_dir="",
        mode=mode,
    )
    graph = build_graph()
    final = graph.invoke(state)
    # LangGraph returns a dict-like AddableValuesDict; normalise.
    if isinstance(final, dict):
        final = PipelineState.model_validate(final)
    console.print(Panel.fit(f"[green]完了[/green]\n出力先: {final.project_dir}"))
    return final


@app.command()
def generate(
    topic: str = typer.Option(..., "--topic", "-t", help="動画のトピック"),
    fmt: str = typer.Option("long", "--format", "-f", help="long | short"),
    keywords: list[str] = typer.Option([], "--keyword", "-k", help="シード語"),
):
    """指定したトピックで動画 1 本を生成する。"""
    _run(topic, Format(fmt), keywords)


@app.command()
def auto(
    fmt: str = typer.Option("long", "--format", "-f", help="long | short"),
    dry_run: bool = typer.Option(False, "--dry-run", help="トレンドの候補だけ表示して生成しない"),
):
    """中小企業庁・経産省・財務省・J-Net21 の RSS からトピックを自動選定して生成する。"""
    from .utils.trends import collect_trends, rank_topics

    items = collect_trends()
    if not items:
        console.print("[yellow]RSS から候補が取れませんでした。手動で --topic を指定してください。[/yellow]")
        raise typer.Exit(1)
    picks = rank_topics(items, n=3)
    if not picks:
        console.print("[yellow]LLM 評価で候補が0件でした。[/yellow]")
        raise typer.Exit(1)

    console.print(Panel.fit("[bold]トレンド候補 Top 3[/bold]"))
    for i, p in enumerate(picks):
        console.print(f"\n[bold]{i+1}.[/bold] {p.get('topic_phrase', '')}")
        console.print(f"   hook: {p.get('hook', '')}")
        console.print(f"   なぜ今: {p.get('why_now', '')}")
        console.print(f"   キーワード: {', '.join(p.get('suggested_keywords', []))}")
        console.print(f"   出典: {p.get('source_url', '')}")

    if dry_run:
        return

    top = picks[0]
    _run(top.get("topic_phrase", ""), Format(fmt), top.get("suggested_keywords", []))


@app.command()
def shorts(
    project: str = typer.Option(..., "--project", "-p"),
    count: int = typer.Option(3, "--count", "-n"),
):
    """既存プロジェクトからショート候補を表示する。"""
    from .utils.paths import project_dir
    p = project_dir(project) / "output" / "shorts" / "PICK_ME.md"
    if not p.exists():
        console.print(f"[red]見つかりません: {p}[/red]")
        raise typer.Exit(1)
    console.print(p.read_text(encoding="utf-8"))


@app.command()
def report(project: str = typer.Option(..., "--project", "-p")):
    """既存プロジェクトのコンプラ最終レポートを表示する。"""
    from .utils.paths import project_dir
    p = project_dir(project) / "compliance" / "final_report.md"
    if not p.exists():
        console.print(f"[red]見つかりません: {p}[/red]")
        raise typer.Exit(1)
    console.print(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    app()

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
def auto():
    """トレンドから自動でトピックを選定して生成する（未実装プレースホルダ）。"""
    console.print("[yellow]auto モードは雛形のみ。Phase 4 でトレンドソース統合予定。[/yellow]")
    _run("最新のインボイス制度動向と中小企業の対策", Format.LONG, ["インボイス", "経過措置"])


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

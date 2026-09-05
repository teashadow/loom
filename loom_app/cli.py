"""CLI for loom — рама конвейера диагностических проб."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .banner import LOOM_BANNER
from .runner import run_pipeline

console = Console()


def _banner() -> None:
    console.print(f"[bold blue]{LOOM_BANNER}[/bold blue]")


class BannerGroup(click.Group):
    def get_help(self, ctx: click.Context) -> str:
        _banner()
        return super().get_help(ctx)


@click.group(cls=BannerGroup)
def main() -> None:
    """MAD pipeline runner — гоняет цепочку проб как подпроцессы, связь файловая."""


@main.command("run")
@click.argument("pipeline", type=click.Path(exists=True))
@click.option("--json", "as_json", type=click.Path(), default=None,
              help="сохранить JSON-агрегат (контракт пайплайна)")
@click.option("--timeout", type=int, default=120, show_default=True,
              help="таймаут на шаг, секунды")
def run_cmd(pipeline: str, as_json: str | None, timeout: int) -> None:
    """Прогнать пайплайн из JSON-спеки. Код возврата = worst rc по шагам."""
    агрегат = run_pipeline(pipeline, report_path=as_json, timeout=timeout)

    if as_json is None:
        # без явного --json всё равно оставим агрегат рядом, чтобы был артефакт
        default_out = Path(pipeline).with_suffix(".loom-report.json")
        default_out.write_text(json.dumps(агрегат, ensure_ascii=False, indent=2), encoding="utf-8")

    table = Table(title=f"loom: {агрегат['инструмент']['цель']}  ·  шагов: {агрегат['шагов']}")
    table.add_column("#"); table.add_column("инструмент"); table.add_column("rc")
    table.add_column("статус"); table.add_column("находок")
    for i, s in enumerate(агрегат["steps"]):
        rc = int(s.get("rc", 2))
        if s.get("dropped"):
            статус, цвет = f"ДРОП: {s.get('почему_drop', '')}", "yellow"
        elif rc == 0:
            статус, цвет = s.get("verdict", "ПРОШЁЛ"), "green"
        elif rc == 1:
            статус, цвет = s.get("verdict", "ПРОВАЛ"), "red"
        else:
            статус, цвет = "НЕ СОСТОЯЛАСЬ", "yellow"
        table.add_row(str(i), str(s.get("tool", "?")), str(rc),
                      f"[{цвет}]{статус}[/{цвет}]", str(s.get("findings_count", 0)))
    console.print(table)

    fo = агрегат["finding_organizer"]
    if fo["доступен"]:
        console.print(f"[dim]finding-organizer: занесено находок {len(fo['занесено_id'])}[/dim]")
    else:
        console.print("[dim]finding-organizer недоступен — агрегат сохранён в JSON[/dim]")

    цвет = {"ПРОВАЛ": "red", "НЕ ПРОВЕРЕНО": "yellow"}.get(агрегат["verdict"], "green")
    console.print(f"Вердикт: [{цвет}]{агрегат['verdict']}[/{цвет}] — {агрегат['почему']}")

    raise SystemExit(int(агрегат["worst_rc"]))


if __name__ == "__main__":
    main()

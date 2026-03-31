#!/usr/bin/env python3
"""CLI tool for reviewing and publishing draft trends."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from pipeline.db import get_trends, update_trend_status, init_db

console = Console()


def show_trend_detail(trend: dict):
    """Display a single trend in detail."""
    console.print()
    console.print(Panel(
        f"[bold]{trend['title_en']}[/bold]\n"
        f"[dim]{trend['title_de'] or 'No DE title'}[/dim]",
        title=f"Trend #{trend['id']} — {trend['status'].upper()}",
        border_style="cyan",
    ))

    # Metadata
    meta = Table(show_header=False, box=None, padding=(0, 2))
    meta.add_column("Key", style="bold")
    meta.add_column("Value")
    meta.add_row("Vertical", trend["primary_vertical"] or "N/A")
    meta.add_row("Verticals", trend["verticals"])
    meta.add_row("PESTEL", trend["pestel"])
    meta.add_row("Tags", trend["tags"])
    meta.add_row("Signal", trend["trend_signal_type"] or "N/A")
    meta.add_row("Mega Trend", trend["mega_trend"] or "N/A")
    meta.add_row("Confidence", f"{trend['confidence']:.2f}" if trend["confidence"] else "N/A")
    meta.add_row("Source", f"{trend['source_name']} — {trend['source_url']}")
    console.print(meta)

    # EN Content
    console.print()
    console.print(Panel(
        f"[bold]Summary:[/bold] {trend['summary_en'] or 'N/A'}\n\n"
        f"{trend['body_en'] or 'No content'}",
        title="English",
        border_style="green",
    ))

    # DE Content
    if trend["body_de"]:
        console.print(Panel(
            f"[bold]Zusammenfassung:[/bold] {trend['summary_de'] or 'N/A'}\n\n"
            f"{trend['body_de']}",
            title="Deutsch",
            border_style="blue",
        ))


def list_trends(status: str | None = None, vertical: str | None = None):
    """List trends in a table."""
    trends = get_trends(status=status, vertical=vertical, limit=50)
    if not trends:
        console.print("[yellow]No trends found.[/yellow]")
        return

    table = Table(title=f"Trends ({len(trends)} found)")
    table.add_column("#", style="dim", width=4)
    table.add_column("Status", width=10)
    table.add_column("Vertical", width=8)
    table.add_column("Title", min_width=40)
    table.add_column("Conf", width=5)
    table.add_column("Source", width=20)

    for t in trends:
        status_style = {
            "draft": "yellow",
            "review": "cyan",
            "published": "green",
            "rejected": "red",
        }.get(t["status"], "white")

        table.add_row(
            str(t["id"]),
            f"[{status_style}]{t['status']}[/{status_style}]",
            t["primary_vertical"] or "?",
            t["title_en"][:60],
            f"{t['confidence']:.1f}" if t["confidence"] else "?",
            (t["source_name"] or "?")[:20],
        )

    console.print(table)


def review_loop():
    """Interactive review loop for draft trends."""
    while True:
        drafts = get_trends(status="draft", limit=20)
        if not drafts:
            console.print("[green]No more drafts to review.[/green]")
            break

        console.print(f"\n[bold]{len(drafts)} drafts remaining[/bold]")
        list_trends(status="draft")

        trend_id = Prompt.ask("\nEnter trend # to review (or 'q' to quit)")
        if trend_id.lower() == "q":
            break

        try:
            tid = int(trend_id)
        except ValueError:
            console.print("[red]Invalid ID[/red]")
            continue

        matching = [t for t in drafts if t["id"] == tid]
        if not matching:
            console.print("[red]Trend not found in drafts[/red]")
            continue

        show_trend_detail(matching[0])

        action = Prompt.ask(
            "\nAction",
            choices=["publish", "reject", "skip", "quit"],
            default="skip",
        )

        if action == "publish":
            update_trend_status(tid, "published")
            console.print(f"[green]Trend #{tid} published![/green]")
        elif action == "reject":
            update_trend_status(tid, "rejected")
            console.print(f"[red]Trend #{tid} rejected.[/red]")
        elif action == "quit":
            break


def main():
    init_db()

    if len(sys.argv) < 2:
        console.print("[bold]Catandary Trends Review CLI[/bold]\n")
        console.print("Commands:")
        console.print("  list [status] [vertical]  — List trends")
        console.print("  show <id>                 — Show trend detail")
        console.print("  publish <id>              — Publish a trend")
        console.print("  reject <id>               — Reject a trend")
        console.print("  review                    — Interactive review loop")
        console.print("  stats                     — Show statistics")
        return

    cmd = sys.argv[1]

    if cmd == "list":
        status = sys.argv[2] if len(sys.argv) > 2 else None
        vertical = sys.argv[3] if len(sys.argv) > 3 else None
        list_trends(status=status, vertical=vertical)

    elif cmd == "show":
        tid = int(sys.argv[2])
        trends = get_trends(limit=100)
        matching = [t for t in trends if t["id"] == tid]
        if matching:
            show_trend_detail(matching[0])
        else:
            console.print("[red]Trend not found[/red]")

    elif cmd == "publish":
        tid = int(sys.argv[2])
        update_trend_status(tid, "published")
        console.print(f"[green]Trend #{tid} published![/green]")

    elif cmd == "reject":
        tid = int(sys.argv[2])
        update_trend_status(tid, "rejected")
        console.print(f"[red]Trend #{tid} rejected.[/red]")

    elif cmd == "review":
        review_loop()

    elif cmd == "stats":
        all_trends = get_trends(limit=1000)
        status_counts = {}
        vertical_counts = {}
        for t in all_trends:
            status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1
            v = t["primary_vertical"] or "?"
            vertical_counts[v] = vertical_counts.get(v, 0) + 1

        console.print("\n[bold]Status Distribution[/bold]")
        for s, c in sorted(status_counts.items()):
            console.print(f"  {s}: {c}")

        console.print("\n[bold]Vertical Distribution[/bold]")
        for v, c in sorted(vertical_counts.items()):
            console.print(f"  {v}: {c}")

        console.print(f"\n[bold]Total:[/bold] {len(all_trends)} trends")

    else:
        console.print(f"[red]Unknown command: {cmd}[/red]")


if __name__ == "__main__":
    main()

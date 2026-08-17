"""grimoire command-line interface (built on typer + rich).

Subcommands: add, rm, list, search, run, show, copy, edit, path, tome.
Bare ``grimoire`` lists everything, grouped by tome.
"""

from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from typing import Annotated

import typer
import typer._click as click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from typer.core import TyperCommand
from typer.main import get_command

from . import __version__
from .search import search
from .store import (
    DEFAULT_TOME,
    CommandNotFound,
    Entry,
    GrimoireError,
    Tome,
    add_command,
    all_entries,
    delete_tome,
    ensure_tome,
    find_entry,
    list_tomes,
    load_tome,
    remove_command,
    save_tome,
    tome_path,
    tomes_dir,
)

app = typer.Typer(
    help="Command cheatsheets: save commands in tomes, search and run them.",
    no_args_is_help=False,
    add_completion=False,
)

tome_app = typer.Typer(help="manage tomes", no_args_is_help=False)


class _IgnoreUnknownOptions(TyperCommand):
    """For `add`: unknown option-like tokens fold into the saved command
    (e.g. `grimoire add flags ls -la --color=auto`)."""

    ignore_unknown_options = True


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _console(*, stderr: bool = False) -> Console:
    # Fresh Console per call so pytest's capsys capture is always honored.
    # highlight=False: user commands/descriptions are arbitrary text, not code.
    return Console(stderr=stderr, highlight=False)


def _echo(text: str) -> None:
    """Print to stderr so `grimoire run x > file` doesn't pollute output."""
    _console(stderr=True).print(text, style="dim")


def onboarding() -> str:
    return (
        "No commands saved yet — add your first spell:\n\n"
        '  grimoire add grep-pid "ps aux | grep -i pid"\n'
        '  grimoire add git:amend --desc "fix up the last commit" "git commit --amend"\n'
        "  grimoire search git\n"
        "  grimoire run grep-pid\n\n"
        f"Tomes live as editable TOML files in {tomes_dir()}"
    )


# ---------------------------------------------------------------------------
# Interactive helpers
# ---------------------------------------------------------------------------


def parse_qualified(arg: str) -> tuple[str | None, str]:
    """Split ``TOME:NAME`` into (tome, name); bare ``NAME`` -> (None, NAME)."""
    if ":" in arg:
        tome, _, name = arg.partition(":")
        if not tome or not name:
            raise GrimoireError(f"invalid name {arg!r} (expected NAME or TOME:NAME)")
        return tome, name
    return None, arg


def pick(entries: list[Entry], prompt: str = "Run") -> Entry | None:
    """Numbered picker over entries; returns None if the user quits."""
    console = _console()
    for i, entry in enumerate(entries, 1):
        desc = f"  {escape(entry.description)}" if entry.description else ""
        console.print(f"  {i:>2}) [cyan]{escape(entry.qualified):<28}[/]{desc}")
    while True:
        try:
            raw = input(f"{prompt} [1-{len(entries)}, q to quit]: ").strip()
        except EOFError:
            return None
        if raw in ("", "q"):
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(entries):
            return entries[int(raw) - 1]
        print(f"  enter a number between 1 and {len(entries)}")


def confirm(question: str, default: bool = False) -> bool:
    """Ask y/N (or Y/n when ``default``); non-interactive returns ``default``."""
    if not sys.stdin.isatty():
        if not default:
            _echo("aborted: cannot prompt (stdin is not a terminal)")
        return default
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(question + suffix).strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _print_entries(tome_name: str, entries: list[Entry]) -> None:
    console = _console()
    if not entries:
        console.print(f"[bold cyan]{escape(tome_name)}:[/] (empty)")
        return
    console.print(f"[bold cyan]{escape(tome_name)}:[/]")
    width = max(len(e.name) for e in entries)
    for entry in sorted(entries, key=lambda e: e.name):
        line = f"  [bold]{escape(entry.name):<{width}}[/]"
        if entry.description:
            line += f"  [dim]{escape(entry.description)}[/]"
        console.print(line)


def _print_search(results: list[Entry]) -> None:
    console = _console()
    width = max(len(e.qualified) for e in results)
    for e in results:
        desc = f"  {escape(e.description)}" if e.description else ""
        console.print(
            f"  [cyan]{escape(e.qualified):<{width}}[/]  [dim]{escape(e.command)}[/]{desc}"
        )


def _print_command(entry: Entry) -> None:
    console = _console()
    lines = [
        f"[bold]tome:[/]      {escape(entry.tome)}",
        f"[bold]name:[/]      {escape(entry.name)}",
        f"[bold]command:[/]   {escape(entry.command)}",
    ]
    if entry.description:
        lines.append(f"[bold]desc:[/]      {escape(entry.description)}")
    if entry.tags:
        lines.append(f"[bold]tags:[/]      {escape(', '.join(entry.tags))}")
    lines.append(f"[bold]file:[/]      {escape(str(tome_path(entry.tome)))}")
    console.print(Panel("\n".join(lines), title="command", border_style="cyan"))


# ---------------------------------------------------------------------------
# Support helpers
# ---------------------------------------------------------------------------


def execute(entry: Entry, print_only: bool = False) -> int:
    _echo(f"$ {entry.command}")
    if print_only:
        print(entry.command)
        return 0
    return subprocess.run(entry.command, shell=True, check=False).returncode


def copy_to_clipboard(text: str) -> bool:
    if sys.platform == "darwin":
        candidates = [["pbcopy"]]
    elif os.name == "nt":
        candidates = [["clip"]]
    else:
        candidates = [
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "-b", "-i"],
        ]
    for argv in candidates:
        try:
            proc = subprocess.run(
                argv, input=text, text=True, capture_output=True, timeout=5, check=False
            )
            if proc.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show the version and exit."),
) -> int | None:
    if version:
        print(f"grimoire {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        return cmd_list(None)  # bare `grimoire` -> list
    return None


@app.command("add", cls=_IgnoreUnknownOptions)
def cmd_add(
    name: Annotated[str, typer.Argument(help="command name, or TOME:NAME")],
    command: Annotated[
        list[str],
        typer.Argument(
            help="shell command to save (quote it, or use -- before option-like words)"
        ),
    ],
    tome: str | None = typer.Option(
        None, "--tome", "-t", help="tome to add to (default: main)"
    ),
    desc: str = typer.Option("", "--desc", "-d", help="short description"),
    tags: str = typer.Option("", "--tags", help="comma-separated tags"),
    force: bool = typer.Option(
        False, "--force", "-f", help="overwrite if the name exists"
    ),
) -> int:
    command_text = " ".join(command)
    if not command_text:
        raise GrimoireError("missing command to save (try: grimoire add NAME -- CMD)")
    target: str = tome or DEFAULT_TOME
    if ":" in name:
        if tome is not None:
            raise GrimoireError("--tome conflicts with TOME:NAME syntax")
        parsed, name = parse_qualified(name)
        assert parsed is not None, "TOME:NAME guarantees a non-empty tome"
        target = parsed
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    add_command(
        target, name, command_text, description=desc, tags=tag_list, force=force
    )
    print(f"saved {target}:{name}")
    return 0


@app.command("rm")
@app.command("remove")
def cmd_remove(
    name: str = typer.Argument(..., help="command name, or TOME:NAME"),
) -> int:
    tome, name = parse_qualified(name)
    if tome is None:
        matches = [e for e in all_entries() if e.name == name]
        if len(matches) == 1:
            remove_command(matches[0].tome, name)
        elif len(matches) > 1:
            where = ", ".join(e.qualified for e in matches)
            raise GrimoireError(
                f"name {name!r} exists in multiple tomes: {where}; use TOME:NAME"
            )
        else:
            raise CommandNotFound(f"no command named {name!r}")
    else:
        remove_command(tome, name)
    print(f"removed {name}")
    return 0


@app.command("list")
@app.command("ls")
def cmd_list(
    tome: str | None = typer.Argument(None, help="only list this tome"),
) -> int:
    if tome:
        t = load_tome(tome)
        entries = [
            Entry(tome, n, c.command, c.description, c.tags)
            for n, c in t.commands.items()
        ]
        _print_entries(tome, entries)
        return 0
    tomes = list_tomes()
    if not tomes:
        print(onboarding())
        return 0
    entries = all_entries()
    for name in tomes:
        _print_entries(name, [e for e in entries if e.tome == name])
    return 0


@app.command("search")
def cmd_search(
    query: str | None = typer.Argument(None, help="search query (picker if omitted)"),
    all_matches: bool = typer.Option(
        False, "--all", help="show every match, not just the top 10"
    ),
) -> int:
    entries = all_entries()
    if not entries:
        print(onboarding())
        return 0
    if not query:
        if not sys.stdin.isatty():
            raise GrimoireError(
                "search needs a query (or run it interactively in a terminal)"
            )
        entry = pick(entries, "Show")
        if entry is None:
            return 1
        print(f"\n{entry.qualified}: {entry.command}")
        return 0
    results = search(entries, query, limit=None if all_matches else 10)
    if not results:
        print(f"no match for {query!r}")
        return 1
    _print_search(results)
    return 0


@app.command("run")
@app.command("exec")
def cmd_run(
    name: str | None = typer.Argument(
        None, help="command name, or TOME:NAME (picker if omitted)"
    ),
    print_only: bool = typer.Option(
        False, "--print", "-p", help="print without running"
    ),
) -> int:
    if name is None:
        entries = all_entries()
        if not entries:
            print(onboarding())
            return 0
        if not sys.stdin.isatty():
            raise GrimoireError("no command name given (and stdin is not a terminal)")
        entry = pick(entries, "Run")
        if entry is None:
            return 1
        return execute(entry, print_only)

    tome, bare_name = parse_qualified(name)
    try:
        entry = find_entry(tome, bare_name)
        return execute(entry, print_only)
    except CommandNotFound:
        entries = search(all_entries(), name, limit=10)
        if not entries:
            raise CommandNotFound(f"no command found matching {name!r}")
        if not sys.stdin.isatty():
            raise GrimoireError(
                f"no exact match for {name!r}; candidates: "
                + ", ".join(e.qualified for e in entries)
            )
        print(f"no exact match for {name!r}; pick one:")
        entry = pick(entries)
        if entry is None:
            return 1
        return execute(entry, print_only)


@app.command("show")
def cmd_show(name: str = typer.Argument(..., help="command name, or TOME:NAME")) -> int:
    tome, name = parse_qualified(name)
    entry = find_entry(tome, name)
    _print_command(entry)
    return 0


@app.command("copy")
def cmd_copy(name: str = typer.Argument(..., help="command name, or TOME:NAME")) -> int:
    tome, name = parse_qualified(name)
    entry = find_entry(tome, name)
    if copy_to_clipboard(entry.command):
        print(f"copied {name} to clipboard")
        return 0
    print(entry.command)
    _echo("no clipboard tool found; printed the command instead")
    return 0


@app.command("edit")
def cmd_edit(
    tome: str | None = typer.Argument(None, help="tome to edit (default: main)"),
) -> int:
    name = tome or DEFAULT_TOME
    path = tome_path(name)
    if not path.exists():
        if not confirm(f"tome {name!r} does not exist — create it?"):
            return 1
        save_tome(Tome(name=name))
    editor = (
        os.environ.get("VISUAL")
        or os.environ.get("EDITOR")
        or ("notepad" if os.name == "nt" else "vi")
    )
    subprocess.call([editor, str(path)])
    return 0


@app.command("path")
def cmd_path() -> int:
    print(tomes_dir())
    return 0


@tome_app.callback(invoke_without_command=True)
def _tome_root(ctx: typer.Context) -> int | None:
    if ctx.invoked_subcommand is None:
        return cmd_tome_list()  # bare `grimoire tome` -> list
    return None


@tome_app.command("new")
def cmd_tome_new(tome: str = typer.Argument(..., help="tome name")) -> int:
    ensure_tome(tome)
    print(f"created tome {tome}")
    return 0


@tome_app.command("rm")
def cmd_tome_rm(
    tome: str = typer.Argument(..., help="tome name"),
    force: bool = typer.Option(
        False, "--force", "-f", help="skip the confirmation prompt"
    ),
) -> int:
    t = load_tome(tome)
    count = len(t.commands)
    # Empty tomes are cheap to recreate: only prompt when it has commands.
    if (
        count
        and not force
        and not confirm(f"remove tome {tome!r} with {count} command(s)?")
    ):
        return 1
    delete_tome(tome)
    print(f"removed tome {tome}")
    return 0


@tome_app.command("list")
def cmd_tome_list() -> int:
    tomes = list_tomes()
    if not tomes:
        print("no tomes yet")
        return 0
    width = max(len(t) for t in tomes)
    console = _console()
    for name in tomes:
        count = len(load_tome(name).commands)
        console.print(f"  [bold]{escape(name):<{width}}[/]  {count} command(s)")
    return 0


app.add_typer(tome_app, name="tome")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _root_command():
    return get_command(app)


def main(argv: list[str] | None = None) -> int:
    try:
        result = _root_command().main(args=argv, standalone_mode=False)
    except GrimoireError as exc:
        _console(stderr=True).print(f"[bold red]grimoire: error:[/] {escape(str(exc))}")
        return 1
    except click.ClickException as exc:
        _console(stderr=True).print(f"[bold red]grimoire: error:[/] {escape(str(exc))}")
        return exc.exit_code
    except typer.Abort:
        return 1
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())

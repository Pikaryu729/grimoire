"""Tome storage: reading and writing TOML files.

Layout
------
Each tome is a single TOML file named ``<tome>.toml`` inside the tomes
directory (see :func:`tomes_dir`). Commands live in a ``cmd`` table keyed
by command name::

    # grimoire tome: main
    [cmd."grep-pid"]
    command = "ps aux | grep -i pid"
    description = "Find a process by name"
    tags = ["process"]

Tome files are human-editable. grimoire reads the keys it knows about and
ignores anything else, so hand-rolled extras won't break loading. Writes
are atomic (write-to-temp + rename).
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TOME = "main"

# Both names are restricted to a safe charset; `:` is excluded so that
# `TOME:NAME` is unambiguous when addressing a command.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class GrimoireError(Exception):
    """Base class for all grimoire errors."""


class TomeNotFound(GrimoireError):
    pass


class CommandNotFound(GrimoireError):
    pass


class CommandExists(GrimoireError):
    pass


class InvalidTome(GrimoireError):
    pass


@dataclass
class Command:
    name: str
    command: str
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> Command:
        tags = data.get("tags", [])
        return cls(
            name=name,
            command=str(data.get("command", "")),
            description=str(data.get("description", "")),
            tags=[str(t) for t in tags] if isinstance(tags, list) else [],
        )


@dataclass
class Tome:
    name: str
    commands: dict[str, Command] = field(default_factory=dict)


@dataclass
class Entry:
    """A command plus the tome it lives in (used for display and search)."""

    tome: str
    name: str
    command: str
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def qualified(self) -> str:
        return f"{self.tome}:{self.name}"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def tomes_dir() -> Path:
    """Directory holding one ``<tome>.toml`` file per tome.

    Resolution order: ``$GRIMOIRE_HOME``, then ``$XDG_CONFIG_HOME/grimoire``,
    then ``~/.config/grimoire``.
    """
    override = os.environ.get("GRIMOIRE_HOME")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "grimoire"
    return Path.home() / ".config" / "grimoire"


def tome_path(tome: str) -> Path:
    return tomes_dir() / f"{tome}.toml"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_tome_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise GrimoireError(
            f"invalid tome name {name!r}: use letters, digits, '.', '_' or '-'"
        )


def validate_command_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise GrimoireError(
            f"invalid command name {name!r}: use letters, digits, '.', '_' or '-'"
        )


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def _toml_string(s: str) -> str:
    """Encode a string as a TOML basic string (safe for tomllib round-trip)."""
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def render_tome(tome: Tome) -> str:
    lines = [f"# grimoire tome: {tome.name}", "# Edit freely; unknown keys are ignored.", ""]
    for name, cmd in sorted(tome.commands.items()):
        lines.append(f'[cmd."{name}"]')
        lines.append(f"command = {_toml_string(cmd.command)}")
        if cmd.description:
            lines.append(f"description = {_toml_string(cmd.description)}")
        if cmd.tags:
            lines.append("tags = [" + ", ".join(_toml_string(t) for t in cmd.tags) + "]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_tome(tome: str) -> Tome:
    validate_tome_name(tome)
    path = tome_path(tome)
    if not path.exists():
        raise TomeNotFound(f"tome {tome!r} does not exist ({path})")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise InvalidTome(
            f"tome {tome!r} is not valid TOML: {exc}\n  fix it with: grimoire edit {tome}"
        ) from exc
    cmd = data.get("cmd")
    if cmd is not None and not isinstance(cmd, dict):
        raise InvalidTome(
            f"tome {tome!r} has an invalid 'cmd' section "
            f"(expected a table, got {type(cmd).__name__})\n"
            f"  fix it with: grimoire edit {tome}"
        )
    commands: dict[str, Command] = {}
    for name, fields in (cmd or {}).items():
        if isinstance(fields, dict):
            commands[name] = Command.from_dict(name, fields)
    return Tome(name=tome, commands=commands)


def save_tome(tome: Tome) -> None:
    validate_tome_name(tome.name)
    tomes_dir().mkdir(parents=True, exist_ok=True)
    path = tome_path(tome.name)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(render_tome(tome), encoding="utf-8")
    tmp.replace(path)


def ensure_tome(tome: str) -> Tome:
    """Load a tome, creating it (empty) if it doesn't exist yet."""
    try:
        return load_tome(tome)
    except TomeNotFound:
        t = Tome(name=tome)
        save_tome(t)
        return t


def list_tomes() -> list[str]:
    directory = tomes_dir()
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.toml"))


def delete_tome(tome: str) -> None:
    validate_tome_name(tome)
    path = tome_path(tome)
    if not path.exists():
        raise TomeNotFound(f"tome {tome!r} does not exist ({path})")
    path.unlink()


# ---------------------------------------------------------------------------
# Command CRUD
# ---------------------------------------------------------------------------


def add_command(
    tome: str,
    name: str,
    command: str,
    description: str = "",
    tags: list[str] | None = None,
    force: bool = False,
) -> None:
    validate_command_name(name)
    t = ensure_tome(tome)
    if name in t.commands and not force:
        raise CommandExists(
            f"{tome}:{name} already exists (use --force to overwrite)"
        )
    t.commands[name] = Command(
        name=name, command=command, description=description, tags=tags or []
    )
    save_tome(t)


def remove_command(tome: str, name: str) -> None:
    t = load_tome(tome)
    if name not in t.commands:
        raise CommandNotFound(f"no command named {tome}:{name}")
    del t.commands[name]
    save_tome(t)


def find_entry(tome: str | None, name: str) -> Entry:
    """Find a command by name, returning the resolved :class:`Entry`.

    With a tome, only that tome is searched. Without one, the default tome
    is preferred, then any single unique match across all tomes. The
    returned Entry always carries the tome the command actually lives in.
    """
    if tome is not None:
        t = load_tome(tome)
        if name in t.commands:
            cmd = t.commands[name]
            return Entry(tome, name, cmd.command, cmd.description, cmd.tags)
        raise CommandNotFound(f"no command named {tome}:{name}")

    try:
        cmd = load_tome(DEFAULT_TOME).commands[name]
        return Entry(DEFAULT_TOME, name, cmd.command, cmd.description, cmd.tags)
    except (TomeNotFound, KeyError):
        pass
    matches = [e for e in all_entries() if e.name == name]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        where = ", ".join(e.qualified for e in matches)
        raise CommandNotFound(f"name {name!r} exists in multiple tomes: {where}")
    raise CommandNotFound(f"no command named {name!r}")


def find_command(tome: str | None, name: str) -> Command:
    """Find a command by name (see :func:`find_entry` for resolution rules)."""
    entry = find_entry(tome, name)
    return Command(
        name=entry.name, command=entry.command, description=entry.description, tags=entry.tags
    )


def all_entries() -> list[Entry]:
    entries: list[Entry] = []
    for tome in list_tomes():
        for name, cmd in load_tome(tome).commands.items():
            entries.append(
                Entry(tome, name, cmd.command, cmd.description, cmd.tags)
            )
    return entries

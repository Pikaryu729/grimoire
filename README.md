# grimoire

A command-line cheatsheet. Save shell commands in **tomes** (editable TOML
files), then search and run them — without leaving the terminal.

```console
$ grimoire add grep-pid "ps aux | grep -i pid"
saved main:grep-pid

$ grimoire add git:amend --desc "fix up the last commit" "git commit --amend"
saved git:amend

$ grimoire search git
  git-amend    git commit --amend
  git-log      git log --oneline

$ grimoire run git-amend
$ git commit --amend
```

Built on [typer](https://typer.tiangolo.com/) and [rich](https://rich.readthedocs.io/)
for a clean CLI surface and good-looking terminal output (tables, panels,
auto color handling, `NO_COLOR` support). Storage and search are pure
stdlib (`tomllib`) and stay dependency-free.

## Install

```console
# uv (preferred)
uv tool install grimoire-cli

# pip / pipx
pip install grimoire-cli
# or from a checkout:
uv pip install -e .
```

The distribution is named `grimoire-cli` (the name `grimoire` is taken on
PyPI); the command is `grimoire`.

## Quickstart

```console
grimoire add NAME COMMAND            # save in the default tome (main)
grimoire add TOME:NAME COMMAND       # save in a specific tome
grimoire add NAME --desc "..." "CMD" # with a description
grimoire add NAME --tags a,b CMD     # with tags (searchable)
grimoire                            # list everything, grouped by tome
grimoire search QUERY                # fuzzy search (name, command, desc, tags)
grimoire run NAME                    # run it
grimoire run                         # interactive picker over all commands
grimoire show NAME                   # full details
grimoire copy NAME                   # copy to clipboard
grimoire rm NAME                     # remove (use TOME:NAME if ambiguous)
grimoire edit [TOME]                 # open a tome in $EDITOR
grimoire tome new TOME               # create a tome
grimoire tome list                   # list tomes with command counts
grimoire tome rm TOME                # delete a tome
grimoire path                        # print the tomes directory
```

Notes:

- Commands are matched by **exact name** first; `run`/`show`/`copy`/`rm`
  also accept `TOME:NAME` when a name isn't unique.
- If `run NAME` has no exact match, you get a numbered picker of fuzzy
  results (or an error listing candidates when stdin isn't a terminal, e.g.
  in scripts).
- `run --print` prints the command without executing it.
- `add` happily saves commands that contain flags:
  `grimoire add flags ls -la --color=auto`. If the command *starts* with
  `-`, separate it with `--`:
  `grimoire add force -- rm -rf --force /tmp/x`.
- `grimoire run` echoes the command to **stderr** before running it, so
  `grimoire run x > out.txt` only captures the command's own output.

## Where things live

Tomes are plain TOML files, one per tome, in a directory that resolves as:

1. `$GRIMOIRE_HOME`
2. `$XDG_CONFIG_HOME/grimoire`
3. `~/.config/grimoire`

```toml
# ~/.config/grimoire/main.toml
# grimoire tome: main
# Edit freely; unknown keys are ignored.

[cmd."grep-pid"]
command = "ps aux | grep -i pid"
description = "Find a process by name"
tags = ["process"]
```

Because they're plain text, tomes are easy to back up, version in git, or
share between machines (`grimoire path` tells you where they are).

Other environment variables: `NO_COLOR` disables ANSI colors; `EDITOR` /
`VISUAL` choose the editor for `grimoire edit`.

## Development

```console
uv sync --extra dev      # install with test deps
uv run pytest            # run the test suite
uv run grimoire --help
```

Requires Python 3.11+.

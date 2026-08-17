# Grimoire

A command-line cheatsheet: save commands in tomes, search and run them.
Python >= 3.11, managed with `uv` (`uv.lock`, `.venv`). Source lives in `src/grimoire/`.

## Validation gates — never finish a task without these passing

Before you consider any task complete, and after any edits to `src/` or `tests/`:

1. **Lint** — `ruff check .`
   - Every error must be fixed. Apply auto-fixable ones with `ruff check --fix`, then re-run.
   - Do not use `# noqa` to silence rules unless it is a deliberate, justified exception; prefer fixing the code.
2. **Type check** — `ty check .`
   - Every diagnostic must be fixed. `ty` has no auto-fixer; resolve each one by correcting the code.

Run the checks against the whole project, not just the files you touched — a change can regress another module's types.

A check passes when it exits 0. Do not report a task as done unless both `ruff check .` and `ty check .` pass.

## Tests

Run `uv run pytest` after changes when practical. Tests are not a hard gate, but a change that breaks them should be flagged to the user.

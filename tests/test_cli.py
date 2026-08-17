import pytest

from grimoire import cli
from grimoire.cli import main
from grimoire.store import load_tome


@pytest.fixture
def home(tmp_path, monkeypatch):
    root = tmp_path / "tomes"
    monkeypatch.setenv("GRIMOIRE_HOME", str(root))
    return root


def run(args, capsys=None):
    code = main(args)
    out = capsys.readouterr() if capsys else None
    return code, out


def test_bare_invocation_shows_onboarding(home, capsys):
    assert main([]) == 0
    assert "grimoire add" in capsys.readouterr().out


def test_add_list_show_rm_flow(home, capsys):
    assert main(["add", "grep-pid", "ps aux | grep -i pid", "--desc", "find pid"]) == 0
    assert main(["add", "work:amend", "--tags", "git,fixup", "git commit --amend"]) == 0

    main(["list"])
    out = capsys.readouterr().out
    assert "main:" in out and "grep-pid" in out
    assert "work:" in out and "amend" in out

    main(["show", "grep-pid"])
    out = capsys.readouterr().out
    assert "ps aux | grep -i pid" in out and "find pid" in out

    assert main(["rm", "grep-pid"]) == 0
    capsys.readouterr()  # drain the "removed ..." message
    main(["list"])
    assert "grep-pid" not in capsys.readouterr().out


def test_add_keeps_command_with_flags(home, capsys):
    # tokens argparse doesn't recognize should be folded into the command
    assert main(["add", "force", "--", "rm -rf --force /tmp/x"]) == 0
    cmd = load_tome("main").commands["force"]
    assert cmd.command == "rm -rf --force /tmp/x"

    assert main(["add", "flags", "ls -la --color=auto"]) == 0
    assert load_tome("main").commands["flags"].command == "ls -la --color=auto"


def test_add_duplicate_requires_force(home, capsys):
    main(["add", "x", "echo one"])
    assert main(["add", "x", "echo two"]) == 1
    assert "already exists" in capsys.readouterr().err
    main(["add", "x", "echo two", "--force"])
    assert load_tome("main").commands["x"].command == "echo two"


def test_add_conflicting_tome_flags(home, capsys):
    assert main(["add", "work:x", "--tome", "other", "echo"]) == 1
    assert "conflicts" in capsys.readouterr().err


def test_search(home, capsys):
    main(["add", "git-log", "--desc", "pretty log", "git log --oneline"])
    main(["add", "git-amend", "git commit --amend"])
    assert main(["search", "git"]) == 0
    out = capsys.readouterr().out
    assert "git-log" in out and "git-amend" in out
    assert main(["search", "pretty"]) == 0
    assert "git-log" in capsys.readouterr().out
    assert main(["search", "nope"]) == 1


def test_run_prints_without_executing(home, capsys):
    main(["add", "hi", "echo hello grimoire"])
    code, out = run(["run", "hi", "--print"], capsys)
    assert code == 0
    assert "echo hello grimoire" in out.out


def test_run_executes_command(monkeypatch, home, capsys):
    main(["add", "hi", "echo hello grimoire"])
    calls = []

    class Dummy:
        returncode = 0

    monkeypatch.setattr(
        cli.subprocess, "run", lambda cmd, shell=True, check=False: calls.append(cmd) or Dummy()
    )
    assert main(["run", "hi"]) == 0
    assert calls == ["echo hello grimoire"]


def test_run_without_exact_match_picks(monkeypatch, home, capsys):
    main(["add", "git-log", "git log"])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "1")

    calls = []

    class Dummy:
        returncode = 0

    monkeypatch.setattr(
        cli.subprocess, "run", lambda cmd, shell=True, check=False: calls.append(cmd) or Dummy()
    )
    assert main(["run", "git"]) == 0  # fuzzy match -> picker -> first result
    assert calls == ["git log"]


def test_run_noninteractive_no_exact_match(home, capsys, monkeypatch):
    main(["add", "git-log", "git log"])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    assert main(["run", "git"]) == 1
    assert "no exact match" in capsys.readouterr().err


def test_qualified_remove(home, capsys):
    main(["add", "work:x", "echo"])
    assert main(["rm", "work:x"]) == 0
    assert "work" not in load_tome("work").commands


def test_tome_management(home, capsys):
    assert main(["tome", "new", "deploy"]) == 0
    assert main(["tome", "list"]) == 0
    out = capsys.readouterr().out
    assert "deploy" in out
    assert main(["tome", "rm", "deploy"]) == 0  # empty tome, no prompt needed
    capsys.readouterr()  # drain the "removed ..." message
    assert main(["tome", "list"]) == 0
    assert "deploy" not in capsys.readouterr().out


def test_copy_falls_back_to_printing(home, capsys, monkeypatch):
    main(["add", "x", "echo hi"])
    monkeypatch.setattr(cli, "copy_to_clipboard", lambda text: False)
    assert main(["copy", "x"]) == 0
    out = capsys.readouterr()
    assert "echo hi" in out.out
    assert "no clipboard tool" in out.err


def test_errors_go_to_stderr(home, capsys):
    assert main(["show", "ghost"]) == 1
    assert "no command named" in capsys.readouterr().err
    assert main(["add", "bad name", "echo"]) == 1
    assert "invalid" in capsys.readouterr().err

import pytest

from grimoire import store


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point grimoire at a throwaway tomes directory."""
    root = tmp_path / "tomes"
    root.mkdir(parents=True)
    monkeypatch.setenv("GRIMOIRE_HOME", str(root))
    return root


def test_roundtrip_preserves_commands(home):
    store.add_command(
        "main",
        "grep-pid",
        'ps aux | grep -i "pid" | grep -v grep',
        description='Find "pid" processes',
        tags=["process", "ps"],
    )
    tome = store.load_tome("main")
    cmd = tome.commands["grep-pid"]
    assert cmd.command == 'ps aux | grep -i "pid" | grep -v grep'
    assert cmd.description == 'Find "pid" processes'
    assert cmd.tags == ["process", "ps"]


def test_roundtrip_escapes_backslashes_and_newlines(home):
    store.add_command("main", "tricky", "printf 'a\\nb\\\\c'\n# comment")
    cmd = store.load_tome("main").commands["tricky"]
    assert cmd.command == "printf 'a\\nb\\\\c'\n# comment"


def test_add_to_qualified_tome(home):
    store.add_command("work", "amend", "git commit --amend")
    assert store.list_tomes() == ["work"]
    assert "amend" in store.load_tome("work").commands


def test_duplicate_add_raises(home):
    store.add_command("main", "x", "echo hi")
    with pytest.raises(store.CommandExists):
        store.add_command("main", "x", "echo bye")
    store.add_command("main", "x", "echo bye", force=True)
    assert store.load_tome("main").commands["x"].command == "echo bye"


def test_tome_not_found(home):
    with pytest.raises(store.TomeNotFound):
        store.load_tome("nope")


def test_command_not_found(home):
    store.add_command("main", "other", "echo")
    with pytest.raises(store.CommandNotFound):
        store.find_command("main", "nope")
    with pytest.raises(store.TomeNotFound):
        store.find_command("ghost", "x")


def test_invalid_toml_reports_helpfully(home):
    (home / "broken.toml").write_text("not = [valid", encoding="utf-8")
    with pytest.raises(store.InvalidTome, match="grimoire edit broken"):
        store.load_tome("broken")


def test_invalid_names_rejected(home):
    with pytest.raises(store.GrimoireError):
        store.add_command("bad name", "x", "echo")
    with pytest.raises(store.GrimoireError):
        store.add_command("main", "a/b", "echo")
    with pytest.raises(store.GrimoireError):
        store.add_command("main", "a:b", "echo")  # ':' reserved for TOME:NAME


def test_find_command_across_tomes(home):
    store.add_command("main", "dup", "echo main")
    store.add_command("work", "dup", "echo work")
    assert store.find_command("work", "dup").command == "echo work"
    assert store.find_command(None, "dup").command == "echo main"  # default tome wins
    store.delete_tome("main")
    assert store.find_command(None, "dup").command == "echo work"  # unique elsewhere
    store.add_command("other", "dup", "echo other")
    with pytest.raises(store.CommandNotFound, match="multiple tomes"):
        store.find_command(None, "dup")
    # unqualified lookup of a name unique to another tome
    store.add_command("work", "only", "echo only")
    assert store.find_command(None, "only").command == "echo only"


def test_delete_tome(home):
    store.add_command("main", "x", "echo")
    store.delete_tome("main")
    assert store.list_tomes() == []
    with pytest.raises(store.TomeNotFound):
        store.delete_tome("main")


def test_remove_command(home):
    store.add_command("main", "x", "echo")
    store.remove_command("main", "x")
    assert store.load_tome("main").commands == {}

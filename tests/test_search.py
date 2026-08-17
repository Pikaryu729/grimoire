from grimoire.search import score, search
from grimoire.store import Entry


def entries():
    return [
        Entry("main", "git-log", "git log --oneline", "Pretty git log", ["git"]),
        Entry("main", "git-amend", "git commit --amend", "Fix last commit", ["git"]),
        Entry("work", "ps-top", "ps aux --sort=-%mem | head", "Top memory processes", ["ps"]),
        Entry("main", "grep-pid", "ps aux | grep -i pid", "Find process by name", ["process"]),
    ]


def test_exact_match():
    assert score("git-log", "git-log") == 1000


def test_prefix_beats_substring():
    s1 = score("git", "git-log")
    s2 = score("git", "big it log")
    assert s1 is not None and s2 is not None
    assert s1 > s2


def test_substring_beats_subsequence():
    s1 = score("log", "git-log")
    s2 = score("glg", "git-log")
    assert s1 is not None and s2 is not None
    assert s1 > s2


def test_no_match():
    assert score("zzz", "git-log") is None


def test_search_ranks_best_first():
    results = search(entries(), "git")
    names = [e.name for e in results]
    # both names prefix-match "git" equally; everything else is excluded
    assert set(names) == {"git-log", "git-amend"}
    assert names == sorted(names)  # deterministic order


def test_exact_name_beats_weaker_matches():
    # "glg" matches git-log's name fuzzily but nothing else
    results = search(entries(), "glg")
    assert results[0].name == "git-log"


def test_search_matches_command_body_and_tags():
    results = search(entries(), "memory")
    assert [e.name for e in results] == ["ps-top"]
    # tag match beats a description substring match
    results = search(entries(), "process")
    assert results[0].name == "grep-pid"


def test_search_fuzzy_subsequence():
    results = search(entries(), "glg")
    assert results[0].name == "git-log"


def test_search_limit():
    results = search(entries(), "git", limit=1)
    assert len(results) == 1


def test_empty_query_matches_nothing():
    assert search(entries(), "") == []

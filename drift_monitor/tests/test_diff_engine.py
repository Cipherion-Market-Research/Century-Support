from drift_monitor.diff_engine import compute_hunks, unified_diff_text


def test_compute_hunks_empty_for_identical_text():
    text = "line one\nline two\nline three"
    assert compute_hunks(text, text) == []


def test_compute_hunks_detects_single_replace():
    old = "a\nsupport@ciphex.io\nc"
    new = "a\nhelp@ciphex.io\nc"
    hunks = compute_hunks(old, new)
    assert len(hunks) == 1
    assert hunks[0].op == "replace"
    assert hunks[0].old_lines == ("support@ciphex.io",)
    assert hunks[0].new_lines == ("help@ciphex.io",)


def test_compute_hunks_detects_insert():
    old = "a\nb"
    new = "a\nb\nc"
    hunks = compute_hunks(old, new)
    assert len(hunks) == 1
    assert hunks[0].op == "insert"
    assert hunks[0].new_lines == ("c",)


def test_unified_diff_text_contains_markers():
    diff = unified_diff_text("a\nb", "a\nc", fromfile="old", tofile="new")
    assert "-b" in diff
    assert "+c" in diff
    assert "old" in diff and "new" in diff

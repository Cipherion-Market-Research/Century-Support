from drift_monitor.diff_engine import compute_hunks
from drift_monitor.fingerprint import fingerprint_hunks


def test_fingerprint_stable_for_same_input():
    old, new = "a\nsupport@ciphex.io\nc", "a\nhelp@ciphex.io\nc"
    hunks = compute_hunks(old, new)
    fp1 = fingerprint_hunks("sample-page", hunks)
    fp2 = fingerprint_hunks("sample-page", compute_hunks(old, new))
    assert fp1 == fp2
    assert len(fp1) == 64  # sha256 hex digest


def test_fingerprint_differs_for_different_slug():
    old, new = "a\nsupport@ciphex.io\nc", "a\nhelp@ciphex.io\nc"
    hunks = compute_hunks(old, new)
    fp_a = fingerprint_hunks("page-a", hunks)
    fp_b = fingerprint_hunks("page-b", hunks)
    assert fp_a != fp_b


def test_fingerprint_differs_for_different_content():
    hunks_1 = compute_hunks("a\nsupport@ciphex.io\nc", "a\nhelp@ciphex.io\nc")
    hunks_2 = compute_hunks("a\nsupport@ciphex.io\nc", "a\nother@ciphex.io\nc")
    assert fingerprint_hunks("p", hunks_1) != fingerprint_hunks("p", hunks_2)

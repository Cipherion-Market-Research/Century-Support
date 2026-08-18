import hashlib
import hmac

from pubs_rag.webhook import relevant_paths_changed, verify_signature


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_accepts_correct_hmac():
    body = b'{"ref": "refs/heads/main"}'
    secret = "test-secret"
    assert verify_signature(secret, body, _sign(secret, body)) is True


def test_verify_signature_rejects_wrong_secret():
    body = b'{"ref": "refs/heads/main"}'
    assert verify_signature("real-secret", body, _sign("wrong-secret", body)) is False


def test_verify_signature_rejects_tampered_body():
    secret = "test-secret"
    signature = _sign(secret, b'{"ref": "refs/heads/main"}')
    assert verify_signature(secret, b'{"ref": "refs/heads/evil"}', signature) is False


def test_verify_signature_rejects_missing_header():
    assert verify_signature("secret", b"body", "") is False


def test_verify_signature_rejects_missing_secret():
    body = b"body"
    assert verify_signature("", body, _sign("anything", body)) is False


def test_relevant_paths_changed_true_for_pdf_asset():
    payload = {"commits": [{"added": ["public/assets/documents/new-report.pdf"], "modified": [], "removed": []}]}
    assert relevant_paths_changed(payload) is True


def test_relevant_paths_changed_true_for_index_page():
    # src/internal-updates.html is the only page in
    # Config.PUBLICATION_INDEX_PATHS: the Insights & Publications section
    # is excluded from the bot's knowledge base per the Bot Parameter
    # Requirements (2026-08-18; see pubs_rag/config.py), so
    # src/insights-and-publications.html is deliberately not watched here.
    payload = {"commits": [{"added": [], "modified": ["src/internal-updates.html"], "removed": []}]}
    assert relevant_paths_changed(payload) is True


def test_relevant_paths_changed_false_for_excluded_insights_publications_page():
    # Even if this page is ever pushed to, it must not trigger a refresh --
    # it's not in Config.PUBLICATION_INDEX_PATHS.
    payload = {
        "commits": [{"added": [], "modified": ["src/insights-and-publications.html"], "removed": []}]
    }
    assert relevant_paths_changed(payload) is False


def test_relevant_paths_changed_false_for_unrelated_file():
    payload = {"commits": [{"added": ["src/js/presale-live.js"], "modified": [], "removed": []}]}
    assert relevant_paths_changed(payload) is False


def test_relevant_paths_changed_false_for_no_commits():
    assert relevant_paths_changed({"commits": []}) is False

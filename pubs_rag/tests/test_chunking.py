import pytest

from pubs_rag.chunking import chunk_text


def test_empty_text_yields_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_is_a_single_chunk():
    text = "one two three four five"
    chunks = chunk_text(text, chunk_size_words=10, overlap_words=2)
    assert chunks == [text]


def test_chunk_boundaries_and_overlap():
    words = [str(i) for i in range(50)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size_words=20, overlap_words=5)

    # every word appears somewhere
    seen = set()
    for c in chunks:
        seen.update(c.split())
    assert seen == set(words)

    # consecutive chunks share exactly the configured overlap
    for a, b in zip(chunks, chunks[1:]):
        a_words = a.split()
        b_words = b.split()
        assert a_words[-5:] == b_words[:5]


def test_no_text_lost_across_chunks():
    text = " ".join(str(i) for i in range(1000))
    chunks = chunk_text(text, chunk_size_words=220, overlap_words=40)
    # last chunk must reach the final word
    assert chunks[-1].split()[-1] == "999"


def test_rejects_overlap_not_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("a b c", chunk_size_words=10, overlap_words=10)

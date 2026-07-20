"""Word-based sliding-window chunker.

Deliberately dependency-free (no langchain-text-splitters) — this service
ships its own requirements.txt independent of the root bot (see
pubs_rag/requirements.txt), and a plain sliding window is sufficient and
easy to reason about for chunk-boundary tests.
"""


def chunk_text(text: str, chunk_size_words: int = 220, overlap_words: int = 40) -> list[str]:
    if overlap_words >= chunk_size_words:
        raise ValueError("overlap_words must be smaller than chunk_size_words")

    words = text.split()
    if not words:
        return []

    step = chunk_size_words - overlap_words
    chunks = []
    i = 0
    while True:
        window = words[i : i + chunk_size_words]
        chunks.append(" ".join(window))
        if i + chunk_size_words >= len(words):
            break
        i += step
    return chunks

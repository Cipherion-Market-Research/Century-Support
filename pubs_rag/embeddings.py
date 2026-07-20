"""Pluggable embedding providers.

Production uses OpenAI (PUBS_RAG_EMBEDDING_PROVIDER=openai, the default —
consistent with core/ai_handler.py's existing use of OpenAI elsewhere in
this codebase). Tests and offline dev use the hashing-trick provider
(PUBS_RAG_EMBEDDING_PROVIDER=local) so the suite never needs a live API key
or network access. Both emit vectors of the same configured dimension so
the pgvector column doesn't change shape when swapping providers.
"""
import hashlib
import math
import re
from abc import ABC, abstractmethod

from pubs_rag.config import Config

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str, dim: int):
        from openai import OpenAI

        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for the openai embedding provider")
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=texts, dimensions=self.dim)
        return [item.embedding for item in response.data]


class HashingEmbeddingProvider(EmbeddingProvider):
    """Deterministic offline embedding via the hashing trick: unigrams and
    bigrams are hashed into fixed-size signed buckets (sign hashing, per
    Weinberger et al. 2009) and L2-normalized. No model download, no
    network call, same result every run — a real, if low-quality,
    embedding rather than a mock."""

    def __init__(self, dim: int = 1536, ngram_range: tuple[int, int] = (1, 2)):
        self.dim = dim
        self._ngram_range = ngram_range

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = _TOKEN_RE.findall(text.lower())
        for n in range(self._ngram_range[0], self._ngram_range[1] + 1):
            for gram in _ngrams(tokens, n):
                digest = hashlib.sha256(gram.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:8], "big") % self.dim
                sign = 1.0 if digest[8] % 2 == 0 else -1.0
                vector[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector


def _ngrams(tokens: list[str], n: int):
    if len(tokens) < n:
        return
    for i in range(len(tokens) - n + 1):
        yield " ".join(tokens[i : i + n])


def get_embedding_provider(config: type = Config) -> EmbeddingProvider:
    provider = config.EMBEDDING_PROVIDER.lower()
    if provider == "openai":
        return OpenAIEmbeddingProvider(config.OPENAI_API_KEY, config.EMBEDDING_MODEL, config.EMBEDDING_DIM)
    if provider == "local":
        return HashingEmbeddingProvider(config.EMBEDDING_DIM)
    raise ValueError(f"unknown PUBS_RAG_EMBEDDING_PROVIDER: {provider!r}")

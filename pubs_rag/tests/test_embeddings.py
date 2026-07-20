import math

from pubs_rag.embeddings import HashingEmbeddingProvider


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def test_deterministic_across_calls():
    provider = HashingEmbeddingProvider(dim=256)
    [a] = provider.embed(["the quick brown fox"])
    [b] = provider.embed(["the quick brown fox"])
    assert a == b


def test_output_dim_matches_config():
    provider = HashingEmbeddingProvider(dim=384)
    [vec] = provider.embed(["hello world"])
    assert len(vec) == 384


def test_vectors_are_l2_normalized():
    provider = HashingEmbeddingProvider(dim=256)
    [vec] = provider.embed(["Ciphex burn cycle deflationary tokenomics"])
    norm = math.sqrt(sum(v * v for v in vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)


def test_empty_text_yields_zero_vector():
    provider = HashingEmbeddingProvider(dim=128)
    [vec] = provider.embed([""])
    assert vec == [0.0] * 128


def test_similar_texts_are_closer_than_dissimilar_ones():
    provider = HashingEmbeddingProvider(dim=1536)
    [burn_a] = provider.embed(["tiered burn activation reduces CPX supply via deflationary burns"])
    [burn_b] = provider.embed(["deflationary token burns and tiered burn rate thresholds"])
    [unrelated] = provider.embed(["leadership team biographies and community social links"])

    assert _cosine(burn_a, burn_b) > _cosine(burn_a, unrelated)

from __future__ import annotations

from app.services.documents.indexing.service import _embed_document_texts
from app.services.retrieval import EmbeddingPurpose, FakeEmbeddingProvider
from app.services.retrieval.embedding import build_embedding_cache_key


class BatchRecordingProvider(FakeEmbeddingProvider):
    def __init__(self) -> None:
        super().__init__()
        self.batch_sizes: list[int] = []

    def embed(self, texts, *, purpose):  # type: ignore[no-untyped-def]
        self.batch_sizes.append(len(texts))
        return super().embed(texts, purpose=purpose)


def test_embedding_batches_over_128_keep_every_text_in_original_order() -> None:
    provider = BatchRecordingProvider()
    texts = tuple(f"合成检索文本-{index:03d}" for index in range(129))

    result = _embed_document_texts(provider, texts)

    assert provider.batch_sizes == [128, 1]
    assert len(result.vectors) == 129
    assert result.cache_keys == tuple(
        build_embedding_cache_key(
            provider.identity,
            EmbeddingPurpose.DOCUMENT,
            text,
        )
        for text in texts
    )
    assert result.purpose is EmbeddingPurpose.DOCUMENT
    assert result.identity == provider.identity

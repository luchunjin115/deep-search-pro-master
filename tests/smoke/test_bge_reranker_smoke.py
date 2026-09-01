from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from app.core.config import BGE_RERANKER_MODEL_ID, BGE_RERANKER_REVISION, Settings
from app.services.retrieval.reranker_provider import (
    BgeRerankerProvider,
    create_reranker_provider,
)
from scripts.download_m2_reranker import ensure_reranker_snapshot

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BGE_RERANKER_SMOKE") != "1",
    reason="set RUN_BGE_RERANKER_SMOKE=1 to load the pinned local Reranker",
)


@pytest.fixture(scope="module")
def provider() -> Iterator[BgeRerankerProvider]:
    settings = Settings(  # type: ignore[call-arg]
        reranker_backend="bge",
        reranker_model=BGE_RERANKER_MODEL_ID,
        reranker_revision=BGE_RERANKER_REVISION,
        model_device="auto",
        model_local_files_only=True,
    )
    ensure_reranker_snapshot(settings.model_cache_root, allow_download=False)
    resolved = create_reranker_provider(settings)
    assert isinstance(resolved, BgeRerankerProvider)
    resolved.load()
    yield resolved


@pytest.mark.parametrize(
    ("query", "related", "unrelated"),
    [
        (
            "蘑菇灯在德国仓还有多少可售库存？",
            "LR-TL-MUSH-OR01 在 DE-FRA 的可售库存为 125。",
            "USB-C扩展坞支持HDMI和千兆网口。",
        ),
        (
            "Which ports are available on the USB-C hub?",
            "The USB-C hub provides HDMI, USB 3.0 and Gigabit Ethernet.",
            "The orange mushroom lamp emits warm bedroom light.",
        ),
        (
            "LR-TL-MUSH-OR01 DE-FRA sellable inventory",
            "SKU LR-TL-MUSH-OR01 | warehouse DE-FRA | sellable 125",
            "SKU DK-HUB-8IN1 | market US | inbound 40",
        ),
    ],
)
def test_real_bge_reranker_orders_multilingual_and_sku_pairs(
    provider: BgeRerankerProvider,
    query: str,
    related: str,
    unrelated: str,
) -> None:
    result = provider.score(query, [related, unrelated])

    assert result.scores[0].raw_score > result.scores[1].raw_score
    assert result.identity.model_id == BGE_RERANKER_MODEL_ID
    assert result.identity.revision == BGE_RERANKER_REVISION
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"

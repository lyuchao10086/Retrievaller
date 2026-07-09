import pytest

from scripts.seed_demo_rag import split_text_into_chunks


def test_split_text_into_chunks_groups_short_paragraphs():
    chunks = split_text_into_chunks(
        "第一段很短。\n\n第二段也很短。\n\n第三段。",
        chunk_size=30,
        chunk_overlap=5,
    )

    assert chunks == ["第一段很短。\n\n第二段也很短。\n\n第三段。"]


def test_split_text_into_chunks_splits_long_paragraphs_with_overlap():
    chunks = split_text_into_chunks(
        "abcdefghijklmnopqrstuvwxyz",
        chunk_size=10,
        chunk_overlap=2,
    )

    assert chunks == ["abcdefghij", "ijklmnopqr", "qrstuvwxyz"]


def test_split_text_into_chunks_rejects_invalid_overlap():
    with pytest.raises(ValueError, match="chunk_overlap"):
        split_text_into_chunks(
            "有效文本",
            chunk_size=10,
            chunk_overlap=10,
        )

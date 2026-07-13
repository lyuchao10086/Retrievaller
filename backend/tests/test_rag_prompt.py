from app.schemas.rag import (
    MultiKnowledgeBaseRagSource,
    MultiKnowledgeBaseRagSourceInfo,
    RagSource,
    RagSourceInfo,
)
from app.services.rag_service import (
    MAX_REFERENCE_CONTENT_CHARS,
    _build_multi_kb_user_prompt,
    _build_user_prompt,
)


def test_build_user_prompt_contains_question_source_and_structured_requirements():
    prompt = _build_user_prompt(
        "宋江的性格特点是什么？",
        [
            RagSource(
                chunk_id="chunk_1",
                document_id="doc_1",
                score=0.8765,
                content="宋江仗义疏财，善于笼络人心。",
                source=RagSourceInfo(
                    file_name="水浒传语料.md",
                    chapter="宋江",
                    section=None,
                    subsection=None,
                ),
            )
        ],
    )

    assert "用户问题：\n宋江的性格特点是什么？" in prompt
    assert "文档：水浒传语料.md - 宋江" in prompt
    assert "Chunk ID：chunk_1" in prompt
    assert "相似度分数：0.8765" in prompt
    assert "先直接回答问题" in prompt
    assert "依据" in prompt
    assert "根据当前知识库资料无法确定" in prompt


def test_build_multi_kb_prompt_contains_knowledge_base_and_document_source():
    prompt = _build_multi_kb_user_prompt(
        "三国演义中诸葛亮做了什么？",
        [
            MultiKnowledgeBaseRagSource(
                chunk_id="chunk_2",
                document_id="doc_2",
                knowledge_base_id="kb_demo",
                score=0.9012,
                content="诸葛亮舌战群儒，并辅佐刘备。",
                source=MultiKnowledgeBaseRagSourceInfo(
                    knowledge_base_name="示例知识库",
                    file_name="三国演义语料.md",
                    chapter="诸葛亮",
                    section="赤壁",
                    subsection=None,
                ),
            )
        ],
    )

    assert "知识库：示例知识库" in prompt
    assert "文档：三国演义语料.md - 诸葛亮 - 赤壁" in prompt
    assert "知识库 ID：kb_demo" in prompt
    assert "Chunk ID：chunk_2" in prompt
    assert "根据当前选择的知识库资料无法确定" in prompt


def test_build_prompt_truncates_long_reference_content():
    long_content = "甲" * (MAX_REFERENCE_CONTENT_CHARS + 100)

    prompt = _build_user_prompt(
        "请总结",
        [
            RagSource(
                chunk_id="chunk_long",
                document_id="doc_long",
                score=0.8,
                content=long_content,
                source=RagSourceInfo(
                    file_name="长文档.txt",
                    chapter=None,
                    section=None,
                    subsection=None,
                ),
            )
        ],
    )

    assert "甲" * MAX_REFERENCE_CONTENT_CHARS in prompt
    assert "内容已截断" in prompt
    assert "甲" * (MAX_REFERENCE_CONTENT_CHARS + 1) not in prompt

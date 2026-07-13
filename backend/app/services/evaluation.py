import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.evaluation import Evaluation
from app.models.qa_record import QaRecord
from app.repositories.evaluation import EvaluationAlreadyExistsError, EvaluationRepository
from app.repositories.qa_record import QaRecordRepository
from app.services.deepseek_service import DeepSeekService
from app.services.knowledge_base import DEFAULT_USER_ID


SYSTEM_PROMPT = """你是一个严格的 RAG 答案评估器。
你的任务是判断一个答案是否完全受到给定参考资料支持。
你不能根据自己的常识补充判断。
你只能根据用户问题、系统答案、参考资料进行评估。
请严格检查：
1. 答案是否忠实于参考资料。
2. 答案是否回答了用户问题。
3. 答案中的引用是否能在参考资料中找到依据。
4. 答案是否遗漏参考资料中的关键内容。
5. 答案是否存在参考资料不支持的幻觉内容。

你必须只输出 JSON，不要输出 Markdown，不要输出解释性前后缀。"""


class QaRecordNotFoundError(ValueError):
    """问答记录不存在或不属于当前用户。"""


class EvaluationNotFoundError(ValueError):
    """评估结果不存在。"""


class DeepSeekInvalidJSONError(ValueError):
    """DeepSeek 返回内容不是合法 JSON。"""

    def __init__(self, raw_response: str):
        super().__init__("DeepSeek returned invalid JSON")
        self.raw_response = raw_response


# 同一 API 进程内合并同一问答记录的并发评估请求，避免重复消耗外部模型调用。
_EVALUATION_LOCKS: dict[tuple[str, str], asyncio.Lock] = {}


async def create_evaluation_for_qa_record(
    qa_record_repository: QaRecordRepository,
    evaluation_repository: EvaluationRepository,
    deepseek_service: DeepSeekService,
    qa_record_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> Evaluation:
    """对一条 RAG 问答记录执行忠实性评估。

    如果已经评估过，直接返回已有结果，避免重复调用 DeepSeek。
    """
    qa_record = await qa_record_repository.get_by_id_and_user(
        qa_record_id,
        user_id,
    )
    if qa_record is None:
        raise QaRecordNotFoundError("Qa record not found")

    lock = _EVALUATION_LOCKS.setdefault((user_id, qa_record_id), asyncio.Lock())
    async with lock:
        existing = await evaluation_repository.get_by_qa_record_id_and_user(
            qa_record_id,
            user_id,
        )
        if existing is not None:
            return existing

        raw_response = await deepseek_service.chat(
            SYSTEM_PROMPT,
            _build_user_prompt(qa_record),
        )
        payload = _parse_evaluation_json(raw_response)
        evaluation = _build_evaluation(qa_record, payload, raw_response, user_id)
        try:
            return await evaluation_repository.insert(evaluation)
        except EvaluationAlreadyExistsError:
            existing = await evaluation_repository.get_by_qa_record_id_and_user(
                qa_record_id,
                user_id,
            )
            if existing is not None:
                return existing
            raise


async def get_evaluation_by_qa_record_id(
    qa_record_repository: QaRecordRepository,
    evaluation_repository: EvaluationRepository,
    qa_record_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> Evaluation:
    """查询指定问答记录的评估结果。"""
    qa_record = await qa_record_repository.get_by_id_and_user(
        qa_record_id,
        user_id,
    )
    if qa_record is None:
        raise QaRecordNotFoundError("Qa record not found")

    evaluation = await evaluation_repository.get_by_qa_record_id_and_user(
        qa_record_id,
        user_id,
    )
    if evaluation is None:
        raise EvaluationNotFoundError("Evaluation not found")
    return evaluation


async def evaluate_answer_content(
    deepseek_service: DeepSeekService,
    *,
    question: str,
    answer: str,
    sources_json: list[dict[str, Any]],
    user_id: str,
) -> dict[str, Any]:
    """Evaluate transient benchmark output without creating a user-visible QA evaluation row."""
    now = _now()
    record = QaRecord(
        id="benchmark_transient",
        user_id=user_id,
        title="benchmark",
        question=question,
        answer=answer,
        knowledge_base_ids=[],
        sources_json=sources_json,
        created_at=now,
        updated_at=now,
    )
    raw_response = await deepseek_service.chat(SYSTEM_PROMPT, _build_user_prompt(record))
    payload = _parse_evaluation_json(raw_response)
    return {
        "faithfulness_score": _score(payload.get("faithfulness_score")),
        "relevance_score": _score(payload.get("relevance_score")),
        "citation_score": _score(payload.get("citation_score")),
        "completeness_score": _score(payload.get("completeness_score")),
        "hallucination": _boolean(payload.get("hallucination")),
        "overall_score": _score(payload.get("overall_score")),
        "reason": str(payload.get("reason") or ""),
    }


async def list_evaluations(
    evaluation_repository: EvaluationRepository,
    user_id: str = DEFAULT_USER_ID,
    limit: int = 50,
) -> list[Evaluation]:
    """查询当前用户最近的评估结果。"""
    return await evaluation_repository.list_recent_by_user(user_id, limit)


def _build_user_prompt(qa_record: QaRecord) -> str:
    sources_text = _format_sources(qa_record.sources_json)
    return f"""用户问题：
{qa_record.question}

系统答案：
{qa_record.answer}

参考资料：
{sources_text}

请输出如下 JSON：

{{
  "faithfulness_score": 1到5的整数,
  "relevance_score": 1到5的整数,
  "citation_score": 1到5的整数,
  "completeness_score": 1到5的整数,
  "hallucination": true或false,
  "overall_score": 1到5的整数,
  "reason": "用中文简要说明评分理由"
}}

评分标准：
5 = 很好，完全符合要求
4 = 基本正确，只有轻微问题
3 = 部分正确，但存在明显不足
2 = 大量内容缺少依据或引用不准确
1 = 严重错误、明显幻觉或没有回答问题"""


def _format_sources(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "参考资料为空。"

    formatted: list[str] = []
    for index, source in enumerate(sources, start=1):
        source_info = source.get("source") or {}
        if not isinstance(source_info, dict):
            source_info = {}
        formatted.append(
            "\n".join(
                [
                    f"[{index}]",
                    f"知识库：{_optional_text(source_info.get('knowledge_base_name'))}",
                    f"文档：{_optional_text(source_info.get('file_name'))}",
                    f"章节：{_optional_text(source_info.get('chapter'))}",
                    f"小节：{_optional_text(source_info.get('section'))}",
                    f"子小节：{_optional_text(source_info.get('subsection'))}",
                    f"原文：{_optional_text(source.get('content'))}",
                ]
            )
        )
    return "\n\n".join(formatted)


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_evaluation_json(raw_response: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise DeepSeekInvalidJSONError(raw_response) from exc
    if not isinstance(payload, dict):
        raise DeepSeekInvalidJSONError(raw_response)
    return payload


def _build_evaluation(
    qa_record: QaRecord,
    payload: dict[str, Any],
    raw_response: str,
    user_id: str,
) -> Evaluation:
    now = _now()
    return Evaluation(
        id=f"eval_{uuid4().hex}",
        user_id=user_id,
        qa_record_id=qa_record.id,
        faithfulness_score=_score(payload.get("faithfulness_score")),
        relevance_score=_score(payload.get("relevance_score")),
        citation_score=_score(payload.get("citation_score")),
        completeness_score=_score(payload.get("completeness_score")),
        hallucination=_boolean(payload.get("hallucination")),
        overall_score=_score(payload.get("overall_score")),
        reason=str(payload.get("reason") or ""),
        raw_response=raw_response,
        created_at=now,
        updated_at=now,
    )


def _score(value: object) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Evaluation score must be an integer between 1 and 5") from exc
    if score < 1 or score > 5:
        raise ValueError("Evaluation score must be between 1 and 5")
    return score


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError("Evaluation hallucination must be a boolean")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

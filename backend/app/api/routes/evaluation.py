from typing import Annotated

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.repositories.evaluation import (
    EvaluationRepository,
    MySQLEvaluationRepository,
)
from app.repositories.qa_record import MySQLQaRecordRepository, QaRecordRepository
from app.schemas.evaluation import EvaluationResponse
from app.services.deepseek_service import (
    DEEPSEEK_API_KEY_NOT_CONFIGURED_MESSAGE,
    DeepSeekAPIError,
    DeepSeekConfigurationError,
    DeepSeekService,
    HttpxDeepSeekService,
)
from app.services.evaluation import (
    DeepSeekInvalidJSONError,
    EvaluationNotFoundError,
    QaRecordNotFoundError,
    create_evaluation_for_qa_record,
    get_evaluation_by_qa_record_id,
)


router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


async def get_qa_record_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> QaRecordRepository:
    """评估前需要查询当前用户的问答记录。"""
    return MySQLQaRecordRepository(connection)


async def get_evaluation_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> EvaluationRepository:
    """评估结果保存和查询 repository。"""
    return MySQLEvaluationRepository(connection)


def get_deepseek_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DeepSeekService:
    """创建 DeepSeek 服务；API key、base URL、模型名都来自环境配置。"""
    return HttpxDeepSeekService(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )


@router.post("/qa-records/{qa_record_id}", response_model=EvaluationResponse)
async def create_evaluation_api(
    qa_record_id: str,
    qa_record_repository: Annotated[
        QaRecordRepository,
        Depends(get_qa_record_repository),
    ],
    evaluation_repository: Annotated[
        EvaluationRepository,
        Depends(get_evaluation_repository),
    ],
    deepseek_service: Annotated[
        DeepSeekService,
        Depends(get_deepseek_service),
    ],
) -> EvaluationResponse:
    """对指定 RAG 问答记录做一次 DeepSeek 忠实性评估。"""
    try:
        evaluation = await create_evaluation_for_qa_record(
            qa_record_repository=qa_record_repository,
            evaluation_repository=evaluation_repository,
            deepseek_service=deepseek_service,
            qa_record_id=qa_record_id,
        )
    except QaRecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Qa record not found",
        ) from exc
    except DeepSeekConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=DEEPSEEK_API_KEY_NOT_CONFIGURED_MESSAGE,
        ) from exc
    except DeepSeekAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except DeepSeekInvalidJSONError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="DeepSeek returned invalid JSON",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return EvaluationResponse.model_validate(evaluation)


@router.get("/qa-records/{qa_record_id}", response_model=EvaluationResponse)
async def get_evaluation_api(
    qa_record_id: str,
    evaluation_repository: Annotated[
        EvaluationRepository,
        Depends(get_evaluation_repository),
    ],
) -> EvaluationResponse:
    """查询指定问答记录的评估结果。"""
    try:
        evaluation = await get_evaluation_by_qa_record_id(
            evaluation_repository,
            qa_record_id,
        )
    except EvaluationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found",
        ) from exc
    return EvaluationResponse.model_validate(evaluation)

import json
from datetime import datetime
from typing import Protocol

import aiomysql

from app.models.knowledge_base_config import (
    GenerationConfig,
    KnowledgeBaseConfig,
    ProcessingConfig,
    RetrievalConfig,
)


class KnowledgeBaseConfigRepository(Protocol):
    async def get_by_knowledge_base_and_user(
        self, knowledge_base_id: str, user_id: str
    ) -> KnowledgeBaseConfig | None: ...

    async def insert(self, config: KnowledgeBaseConfig) -> KnowledgeBaseConfig: ...

    async def update(self, config: KnowledgeBaseConfig) -> KnowledgeBaseConfig: ...


class MySQLKnowledgeBaseConfigRepository:
    def __init__(self, connection: aiomysql.Connection):
        self.connection = connection

    async def get_by_knowledge_base_and_user(
        self, knowledge_base_id: str, user_id: str
    ) -> KnowledgeBaseConfig | None:
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT knowledge_base_id, user_id, processing_config_json,
                       retrieval_config_json, generation_config_json, version,
                       created_at, updated_at
                FROM knowledge_base_configs
                WHERE knowledge_base_id = %s AND user_id = %s
                LIMIT 1
                """,
                (knowledge_base_id, user_id),
            )
            row = await cursor.fetchone()
        return None if row is None else self._from_row(row)

    async def insert(self, config: KnowledgeBaseConfig) -> KnowledgeBaseConfig:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO knowledge_base_configs (
                    knowledge_base_id, user_id, processing_config_json,
                    retrieval_config_json, generation_config_json, version,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    config.knowledge_base_id,
                    config.user_id,
                    json.dumps(config.processing_dict(), ensure_ascii=False),
                    json.dumps(config.retrieval_dict(), ensure_ascii=False),
                    json.dumps(config.generation_dict(), ensure_ascii=False),
                    config.version,
                    config.created_at,
                    config.updated_at,
                ),
            )
        await self.connection.commit()
        return config

    async def update(self, config: KnowledgeBaseConfig) -> KnowledgeBaseConfig:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE knowledge_base_configs
                SET processing_config_json = %s,
                    retrieval_config_json = %s,
                    generation_config_json = %s,
                    version = %s,
                    updated_at = %s
                WHERE knowledge_base_id = %s AND user_id = %s
                """,
                (
                    json.dumps(config.processing_dict(), ensure_ascii=False),
                    json.dumps(config.retrieval_dict(), ensure_ascii=False),
                    json.dumps(config.generation_dict(), ensure_ascii=False),
                    config.version,
                    config.updated_at,
                    config.knowledge_base_id,
                    config.user_id,
                ),
            )
            if cursor.rowcount == 0:
                raise LookupError("Knowledge base configuration not found")
        await self.connection.commit()
        return config

    @staticmethod
    def _from_row(row: dict[str, object]) -> KnowledgeBaseConfig:
        processing = json.loads(str(row["processing_config_json"]))
        retrieval = json.loads(str(row["retrieval_config_json"]))
        generation = json.loads(str(row["generation_config_json"]))
        return KnowledgeBaseConfig(
            knowledge_base_id=str(row["knowledge_base_id"]),
            user_id=str(row["user_id"]),
            processing=ProcessingConfig(**processing),
            retrieval=RetrievalConfig(**retrieval),
            generation=GenerationConfig(**generation),
            version=int(row["version"]),
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else None,
            updated_at=row["updated_at"] if isinstance(row["updated_at"], datetime) else None,
        )

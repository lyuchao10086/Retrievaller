from typing import Protocol
from uuid import uuid4

from app.models.chunk import Chunk


class VectorSearchResult:
    """Milvus 检索返回的轻量结果。"""

    def __init__(
        self,
        chunk_id: str,
        document_id: str,
        knowledge_base_id: str,
        user_id: str,
        score: float,
    ):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.knowledge_base_id = knowledge_base_id
        self.user_id = user_id
        self.score = score


class VectorService(Protocol):
    """向量数据库写入和检索接口。"""

    def insert_chunk_embeddings(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> list[str]:
        raise NotImplementedError

    def search_chunk_embeddings(
        self,
        query_embedding: list[float],
        user_id: str,
        knowledge_base_id: str,
        top_k: int,
    ) -> list[VectorSearchResult]:
        raise NotImplementedError

    def search_chunk_embeddings_in_knowledge_bases(
        self,
        query_embedding: list[float],
        user_id: str,
        knowledge_base_ids: list[str],
        top_k: int,
    ) -> list[VectorSearchResult]:
        raise NotImplementedError


class MilvusVectorService:
    """Milvus document_chunks collection 写入实现。"""

    def __init__(
        self,
        host: str,
        port: int,
        collection_name: str,
        embedding_dimension: int,
    ):
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.embedding_dimension = embedding_dimension

    def insert_chunk_embeddings(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> list[str]:
        """写入 chunk embedding，并返回每条记录的 vector_id。"""
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings size mismatch")

        collection = self._get_or_create_collection()
        vector_ids = [f"vec_{uuid4().hex}" for _ in chunks]
        collection.insert(
            [
                vector_ids,
                embeddings,
                [chunk.id for chunk in chunks],
                [chunk.document_id for chunk in chunks],
                [chunk.knowledge_base_id for chunk in chunks],
                [chunk.user_id for chunk in chunks],
            ]
        )
        collection.flush()
        return vector_ids

    def search_chunk_embeddings(
        self,
        query_embedding: list[float],
        user_id: str,
        knowledge_base_id: str,
        top_k: int,
    ) -> list[VectorSearchResult]:
        """在指定知识库沙箱内检索相似 chunk embedding。"""
        collection = self._get_or_create_collection()
        expr = (
            f'user_id == "{_escape_expr_value(user_id)}" '
            f'&& knowledge_base_id == "{_escape_expr_value(knowledge_base_id)}"'
        )
        results = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {}},
            limit=top_k,
            expr=expr,
            output_fields=[
                "chunk_id",
                "document_id",
                "knowledge_base_id",
                "user_id",
            ],
        )
        if not results:
            return []

        search_results: list[VectorSearchResult] = []
        for hit in results[0]:
            entity = hit.entity
            search_results.append(
                VectorSearchResult(
                    chunk_id=str(entity.get("chunk_id")),
                    document_id=str(entity.get("document_id")),
                    knowledge_base_id=str(entity.get("knowledge_base_id")),
                    user_id=str(entity.get("user_id")),
                    score=float(hit.score),
                )
            )
        return search_results

    def search_chunk_embeddings_in_knowledge_bases(
        self,
        query_embedding: list[float],
        user_id: str,
        knowledge_base_ids: list[str],
        top_k: int,
    ) -> list[VectorSearchResult]:
        """在多个指定知识库沙箱内检索相似 chunk embedding。"""
        if not knowledge_base_ids:
            return []

        collection = self._get_or_create_collection()
        kb_values = ", ".join(
            f'"{_escape_expr_value(kb_id)}"' for kb_id in knowledge_base_ids
        )
        expr = (
            f'user_id == "{_escape_expr_value(user_id)}" '
            f"&& knowledge_base_id in [{kb_values}]"
        )
        results = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {}},
            limit=top_k,
            expr=expr,
            output_fields=[
                "chunk_id",
                "document_id",
                "knowledge_base_id",
                "user_id",
            ],
        )
        if not results:
            return []

        search_results: list[VectorSearchResult] = []
        for hit in results[0]:
            entity = hit.entity
            search_results.append(
                VectorSearchResult(
                    chunk_id=str(entity.get("chunk_id")),
                    document_id=str(entity.get("document_id")),
                    knowledge_base_id=str(entity.get("knowledge_base_id")),
                    user_id=str(entity.get("user_id")),
                    score=float(hit.score),
                )
            )
        return search_results

    def _get_or_create_collection(self):
        """确保 Milvus collection 存在，并返回 collection 对象。"""
        from pymilvus import (
            Collection,
            CollectionSchema,
            DataType,
            FieldSchema,
            connections,
            utility,
        )

        connections.connect(
            alias="default",
            host=self.host,
            port=str(self.port),
        )
        if utility.has_collection(self.collection_name):
            collection = Collection(self.collection_name)
            collection.load()
            return collection

        fields = [
            FieldSchema(
                name="id",
                dtype=DataType.VARCHAR,
                max_length=128,
                is_primary=True,
            ),
            FieldSchema(
                name="embedding",
                dtype=DataType.FLOAT_VECTOR,
                dim=self.embedding_dimension,
            ),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(
                name="knowledge_base_id",
                dtype=DataType.VARCHAR,
                max_length=128,
            ),
            FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=128),
        ]
        schema = CollectionSchema(
            fields=fields,
            description="RAG document chunk embeddings",
        )
        collection = Collection(self.collection_name, schema=schema)
        collection.create_index(
            field_name="embedding",
            index_params={
                "index_type": "AUTOINDEX",
                "metric_type": "COSINE",
                "params": {},
            },
        )
        collection.load()
        return collection


def _escape_expr_value(value: str) -> str:
    """转义 Milvus 字符串过滤表达式中的双引号。"""
    return value.replace('"', '\\"')

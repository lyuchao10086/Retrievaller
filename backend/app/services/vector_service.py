from typing import Protocol
from uuid import uuid4

from app.models.chunk import Chunk


class VectorService(Protocol):
    """向量数据库写入接口。"""

    def insert_chunk_embeddings(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> list[str]:
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

import asyncio
from io import BytesIO
from typing import Protocol

from minio import Minio


class DocumentStorage(Protocol):
    """文档原始文件存储接口，方便测试时替换 MinIO。"""

    async def ensure_bucket(self, bucket_name: str) -> None:
        raise NotImplementedError

    async def put_object(
        self,
        bucket_name: str,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        raise NotImplementedError

    async def get_object(self, bucket_name: str, object_key: str) -> bytes:
        raise NotImplementedError


class MinIODocumentStorage:
    """MinIO 对象存储实现，用于保存上传的原始文件。"""

    def __init__(self, client: Minio):
        self.client = client

    async def ensure_bucket(self, bucket_name: str) -> None:
        """确保 bucket 存在，不存在时自动创建。"""
        exists = await asyncio.to_thread(self.client.bucket_exists, bucket_name)
        if not exists:
            await asyncio.to_thread(self.client.make_bucket, bucket_name)

    async def put_object(
        self,
        bucket_name: str,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        """把原始文件字节写入 MinIO。"""
        await asyncio.to_thread(
            self.client.put_object,
            bucket_name,
            object_key,
            BytesIO(data),
            len(data),
            content_type=content_type,
        )

    async def get_object(self, bucket_name: str, object_key: str) -> bytes:
        """从 MinIO 读取对象字节，用于后台解析原始文件。"""
        response = await asyncio.to_thread(
            self.client.get_object,
            bucket_name,
            object_key,
        )
        try:
            return await asyncio.to_thread(response.read)
        finally:
            response.close()
            response.release_conn()

from typing import Protocol


class ParseTaskDispatcher(Protocol):
    """解析任务投递接口，便于 API 测试时替换成假的 dispatcher。"""

    def submit(self, kb_id: str, document_id: str, user_id: str) -> str:
        raise NotImplementedError


class CeleryParseTaskDispatcher:
    """使用 Celery 把解析任务投递到后台 worker。"""

    def submit(self, kb_id: str, document_id: str, user_id: str) -> str:
        # 延迟导入避免单元测试加载路由时就初始化 Celery 任务模块。
        from app.tasks.document_tasks import parse_document_task

        async_result = parse_document_task.delay(kb_id, document_id, user_id)
        return str(async_result.id)

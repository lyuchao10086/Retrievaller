import contextvars
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any


_log_context: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "retrievaller_log_context",
    default={},
)
_CONTEXT_FIELDS = ("request_id", "user_id", "knowledge_base_id", "document_id", "task_id", "error_code")
_SENSITIVE_EXCEPTION_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;\"']+"),
    re.compile(r"(?i)(\bbearer\s+)[^\s,;\"']+"),
    re.compile(r"(?i)(\b(?:password|api[_-]?key|token|secret)\s*[:=]\s*)[^\s,;\"']+"),
)


def bind_log_context(**values: str | None) -> contextvars.Token[dict[str, str]]:
    context = dict(_log_context.get())
    context.update({key: value for key, value in values.items() if value})
    return _log_context.set(context)


def reset_log_context(token: contextvars.Token[dict[str, str]]) -> None:
    _log_context.reset(token)


class JsonFormatter(logging.Formatter):
    """Emit request-correlated logs without serializing bodies or credentials."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = dict(_log_context.get())
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None) or context.get(field)
            if value:
                payload[field] = _mask_user_id(str(value)) if field == "user_id" else str(value)
        for field in ("http_method", "path", "status_code", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = _redact_exception_text(
                self.formatException(record.exc_info)
            )
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_level: str, log_format: str) -> None:
    handler = logging.StreamHandler()
    if log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        handlers=[handler],
        force=True,
    )


def _mask_user_id(user_id: str) -> str:
    if len(user_id) <= 4:
        return "***"
    return f"{user_id[:3]}***{user_id[-2:]}"


def _redact_exception_text(value: str) -> str:
    for pattern in _SENSITIVE_EXCEPTION_PATTERNS:
        value = pattern.sub(r"\1[REDACTED]", value)
    return value

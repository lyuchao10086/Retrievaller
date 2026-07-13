import logging
import sys

from app.core.logging import JsonFormatter, bind_log_context, reset_log_context


def test_json_logs_mask_user_id_and_ignore_unstructured_sensitive_extras():
    token = bind_log_context(request_id="request-123", user_id="usr_sensitive")
    try:
        record = logging.getLogger("test").makeRecord(
            "test",
            logging.INFO,
            __file__,
            0,
            "document_processing_started",
            (),
            None,
            extra={"password": "secret-password", "authorization": "Bearer secret-token"},
        )
        output = JsonFormatter().format(record)
    finally:
        reset_log_context(token)

    assert "usr***ve" in output
    assert "secret-password" not in output
    assert "secret-token" not in output


def test_json_logs_redact_sensitive_values_from_exception_tracebacks():
    try:
        raise RuntimeError(
            "request failed with Authorization: Bearer secret-token and password=secret-password"
        )
    except RuntimeError:
        exc_info = sys.exc_info()

    record = logging.getLogger("test").makeRecord(
        "test",
        logging.ERROR,
        __file__,
        0,
        "request_failed",
        (),
        exc_info,
    )

    output = JsonFormatter().format(record)

    assert "secret-token" not in output
    assert "secret-password" not in output
    assert "[REDACTED]" in output

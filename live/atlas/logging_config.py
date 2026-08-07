"""
Structured (JSON) logging for atlas.main:app (Sprint 10). Railway's log viewer (and
any real log aggregator downstream of it) can filter/search JSON logs by field far
more effectively than the plain "%(asctime)s %(levelname)s ..." text format used since
Sprint 1 - one JSON object per line: timestamp, level, logger name, message, plus any
extra fields a call site attached via `logger.info(..., extra={...})`.

Deliberately NOT used by scripts/dev_seed_server.py - that's a local, human-read
terminal tool where the original human-readable text format stays more convenient.
This module is for the real production entrypoint (atlas.main), where logs are read by
a log viewer/aggregator, not a person tailing a terminal in real time.
"""
import json
import logging
from datetime import datetime, timezone

# Attributes every standard LogRecord already carries - anything else present on a
# record was attached via `extra={...}` at the call site, and gets folded into the
# JSON output as its own top-level field (e.g. correlation_id, event_type).
_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class _PsycopgPoolSanitizer(logging.Filter):
    """Keep driver connection diagnostics out of the application log boundary."""

    _SAFE_MESSAGE = "postgres_pool_event"

    def filter(self, record: logging.LogRecord) -> bool:
        # psycopg-pool formats connection details (host, port, and driver
        # exceptions) in the message before it reaches our handlers. Keep the
        # level/logger for operator triage, but discard all untrusted payloads.
        record.msg = self._SAFE_MESSAGE
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def _install_psycopg_pool_sanitizer() -> None:
    pool_logger = logging.getLogger("psycopg.pool")
    if not any(isinstance(item, _PsycopgPoolSanitizer) for item in pool_logger.filters):
        pool_logger.addFilter(_PsycopgPoolSanitizer())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}
        payload.update(extra)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Replaces the root logger's handlers with a single JSON-formatted stream
    handler. Idempotent - safe to call more than once (e.g. across repeated test
    imports), always ends with exactly one handler installed."""
    _install_psycopg_pool_sanitizer()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

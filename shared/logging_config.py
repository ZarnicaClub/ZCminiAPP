"""Единое логирование: JSON + correlation trace_id."""
import logging
import sys
from contextvars import ContextVar

trace_id_var: ContextVar = ContextVar("trace_id", default=None)

try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # pragma: no cover
    JsonFormatter = None


def set_trace_id(tid: str):
    trace_id_var.set(tid)


def get_trace_id():
    return trace_id_var.get()


class _TraceInjectingFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = get_trace_id() or "-"
        return True


def setup_logging(level: int = logging.INFO):
    handler = logging.StreamHandler(sys.stdout)
    if JsonFormatter is not None:
        handler.setFormatter(
            JsonFormatter("%(asctime)s %(levelname)s %(name)s %(trace_id)s %(message)s")
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(trace_id)s | %(message)s")
        )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for h in root.handlers:
        h.addFilter(_TraceInjectingFilter())

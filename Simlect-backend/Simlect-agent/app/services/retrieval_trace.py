"""Task-local retrieval status; no queries, identifiers, or credentials are logged."""
from contextvars import ContextVar
_trace=ContextVar('product_retrieval_status',default=None)
def start():_trace.set({'keyword':'NOT_STARTED','vector':'NOT_STARTED'})
def mark(part,status):
    if _trace.get() is not None:_trace.set({**_trace.get(),part:status})
def snapshot():return dict(_trace.get() or {})

import bisect
import contextlib
import json
import sys
import time
import weakref
from collections.abc import Callable
from functools import wraps
from itertools import dropwhile
from types import (
    BuiltinFunctionType,
    ClassMethodDescriptorType,
    CodeType,
    FunctionType,
    GetSetDescriptorType,
    MemberDescriptorType,
    MethodDescriptorType,
    MethodType,
    MethodWrapperType,
    WrapperDescriptorType,
)

__all__ = ["tracer", "setup_tracing", "teardown_tracing", "write_events", "traceable"]

MONITORING = sys.monitoring
EVENTS = MONITORING.events

_FTYPE_TO_CAT: dict[type, str] = {
    FunctionType: "py_function",
    MethodType: "py_method",
    BuiltinFunctionType: "builtin_function",
    MethodDescriptorType: "method_descriptor",
    MethodWrapperType: "method_wrapper",
    ClassMethodDescriptorType: "classmethod_descriptor",
    WrapperDescriptorType: "wrapper_descriptor",
    GetSetDescriptorType: "getset_descriptor",
    MemberDescriptorType: "member_descriptor",
    type: "type",
}
_line_cache: dict[CodeType, tuple[tuple[int, ...], tuple[int, ...]]] = {}
_raw_events: list[tuple]
_profiler_min_ts: int


def _get_callable_name(callable: object) -> str:
    if isinstance(callable, weakref.CallableProxyType):
        return getattr(callable.__call__, "__qualname__", str(callable.__call__))
    elif isinstance(callable, weakref.ReferenceType):
        return getattr(callable.__callback__, "__qualname__", str(callable.__callback__))
    else:
        return getattr(callable, "__qualname__", str(callable))


def _get_lineno(code: CodeType, instruction_offset: int) -> int:
    if code not in _line_cache:
        _, ends, linenos = zip(*code.co_lines())
        _line_cache[code] = (ends, linenos)
    else:
        ends, linenos = _line_cache[code]
    _, ends, linenos = zip(*code.co_lines())
    return linenos[bisect.bisect_left(ends, instruction_offset)]


def _cb_call(code: CodeType, instruction_offset: int, callable: object, arg0: object) -> None:
    _raw_events.append(
        (
            EVENTS.CALL,
            time.perf_counter_ns(),
            code,
            instruction_offset,
            callable,
            arg0,
        )
    )


def _cb_c_return(code: CodeType, instruction_offset: int, callable: object, arg0: object) -> None:
    _raw_events.append(
        (
            EVENTS.C_RETURN,
            time.perf_counter_ns(),
            code,
            instruction_offset,
            callable,
            arg0,
        )
    )


def _cb_c_raise(code: CodeType, instruction_offset: int, callable: object, arg0: object) -> None:
    pass


def _cb_py_start(code: CodeType, instruction_offset: int) -> None:
    _raw_events.append(
        (
            EVENTS.PY_START,
            time.perf_counter_ns(),
            code,
            instruction_offset,
        )
    )


def _cb_py_return(code: CodeType, instruction_offset: int, retval: object) -> None:
    _raw_events.append(
        (
            EVENTS.PY_RETURN,
            time.perf_counter_ns(),
            code,
            instruction_offset,
            retval,
        )
    )


def setup_tracing() -> None:
    global _profiler_min_ts
    _profiler_min_ts = time.perf_counter_ns()
    global _raw_events
    _raw_events = []
    MONITORING.use_tool_id(MONITORING.PROFILER_ID, "profiler")
    MONITORING.register_callback(MONITORING.PROFILER_ID, EVENTS.CALL, _cb_call)
    MONITORING.register_callback(MONITORING.PROFILER_ID, EVENTS.C_RETURN, _cb_c_return)
    MONITORING.register_callback(MONITORING.PROFILER_ID, EVENTS.C_RAISE, _cb_c_raise)
    MONITORING.register_callback(MONITORING.PROFILER_ID, EVENTS.PY_START, _cb_py_start)
    MONITORING.register_callback(MONITORING.PROFILER_ID, EVENTS.PY_RETURN, _cb_py_return)
    MONITORING.set_events(
        MONITORING.PROFILER_ID,
        EVENTS.CALL | EVENTS.C_RETURN | EVENTS.C_RAISE | EVENTS.PY_START | EVENTS.PY_RETURN,
    )


def teardown_tracing() -> None:
    MONITORING.set_events(MONITORING.PROFILER_ID, EVENTS.NO_EVENTS)
    for event in (
        EVENTS.CALL,
        EVENTS.C_RETURN,
        EVENTS.C_RAISE,
        EVENTS.PY_START,
        EVENTS.PY_RETURN,
    ):
        MONITORING.register_callback(MONITORING.PROFILER_ID, event, None)
    MONITORING.free_tool_id(MONITORING.PROFILER_ID)


def write_events(filename: str = "trace.json") -> None:
    global _raw_events
    global _profiler_min_ts
    for i in range(len(_raw_events) - 1, -1, -1):
        # Remove any dangling start events
        if _raw_events[i][0] in (EVENTS.PY_START, EVENTS.CALL):
            _raw_events.pop()
        else:
            break

    chrome_events = []
    event_stack = []
    for event_type, ts, *args in dropwhile(lambda x: x[0] not in (EVENTS.PY_START, EVENTS.CALL), _raw_events):
        if event_type == EVENTS.CALL:
            code, instruction_offset, callable, arg0 = args
            cat = _FTYPE_TO_CAT.get(type(callable), type(callable).__qualname__)
            lineno = _get_lineno(code, instruction_offset)
            callable_name = _get_callable_name(callable)
            name = f"{code.co_filename}:{lineno}:{callable_name}"
            chrome_events.append(
                {
                    "name": name,
                    "cat": cat,
                    "ph": "B",
                    "ts": (ts - _profiler_min_ts) / 1000,
                    "pid": 0,
                    "tid": 0,
                    "args": {"arg0": ("MISSING" if arg0 is MONITORING.MISSING else arg0.__class__.__qualname__)},
                }
            )
            event_stack.append(len(chrome_events) - 1)
        elif event_type == EVENTS.C_RETURN:
            code, instruction_offset, callable, arg0 = args
            lineno = _get_lineno(code, instruction_offset)
            callable_name = _get_callable_name(callable)
            name = f"{code.co_filename}:{lineno}:{callable_name}"

            # Remove any dangling "B" events that don't have a corresponding "E" event
            idx = event_stack.pop()
            while name != chrome_events[idx]["name"]:
                chrome_events.pop(idx)
                idx = event_stack.pop()

            chrome_events.append(
                {
                    "name": name,
                    "ph": "E",
                    "ts": (ts - _profiler_min_ts) / 1000,
                    "cat": "c_return",
                    "pid": 0,
                    "tid": 0,
                    "args": {"retval": ("MISSING" if arg0 is MONITORING.MISSING else arg0.__class__.__qualname__)},
                }
            )
        elif event_type == EVENTS.PY_START:
            code, instruction_offset = args
            name = f"{code.co_filename}:{code.co_firstlineno}:{code.co_qualname}"
            chrome_events.append(
                {
                    "name": name,
                    "ph": "B",
                    "ts": (ts - _profiler_min_ts) / 1000,
                    "cat": "py_start",
                    "pid": 0,
                    "tid": 0,
                    "args": (
                        chrome_events[-1]["args"] if chrome_events[-1]["cat"] in ("py_function", "py_method") else {}
                    ),
                }
            )
            event_stack.append(len(chrome_events) - 1)
        elif event_type == EVENTS.PY_RETURN:
            code, instruction_offset, retval = args
            name = f"{code.co_filename}:{code.co_firstlineno}:{code.co_qualname}"

            # Remove any dangling "B" events that don't have a corresponding "E" event
            idx = event_stack.pop()
            while name != chrome_events[idx]["name"]:
                chrome_events.pop(idx)
                idx = event_stack.pop()

            chrome_events.append(
                {
                    "name": name,
                    "ph": "E",
                    "ts": (ts - _profiler_min_ts) / 1000,
                    "cat": "py_return",
                    "pid": 0,
                    "tid": 0,
                    "args": {"retval": retval.__class__.__qualname__},
                }
            )
    for idx in reversed(event_stack):
        # In theory there should only be at most one event left in the stack
        chrome_events.pop(idx)

    chrome_events.extend(
        [
            {
                "name": "process_name",
                "ph": "M",
                "pid": 0,
                "tid": 0,
                "args": {"name": "python"},
            },
            {
                "name": "thread_name",
                "ph": "M",
                "pid": 0,
                "tid": 0,
                "args": {"name": "MainThread"},
            },
        ]
    )
    with open(filename, "w") as f:
        json.dump({"traceEvents": chrome_events}, f, separators=(",", ":"))


@contextlib.contextmanager
def tracer(filename: str = "trace.json"):
    setup_tracing()
    try:
        yield
    finally:
        teardown_tracing()
        write_events(filename)


def traceable[T, **P](func: Callable[P, T], prefix: str = "") -> Callable[P, T]:
    @wraps(func)
    def wrapper(*args, **kwargs):
        with tracer(f"{prefix}{func.__qualname__}.json"):
            return func(*args, **kwargs)

    return wrapper

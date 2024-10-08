# Simple Tracer

A simple tracer for Python programs using the `sys.monitoring` namespace
[introduced in Python 3.12](https://docs.python.org/3/whatsnew/3.12.html#pep-669-low-impact-monitoring-for-cpython).
The tracer exports to the [Chrome Trace event format](https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/preview).

## Installation

```shell
pip install simple-tracer
```

## Usage

As a context manager:

```python
from simple_tracer import tracer

with tracer("trace.json"):
    func()
```

or, as a function decorator

```python
from simple_tracer import traceable

@traceable
def square(x: int) -> int:
    return x**2
```

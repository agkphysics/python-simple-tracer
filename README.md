# Simple Tracer

A simple tracer for Python programs using the `sys.monitoring` namespace
[introduced in Python
3.12](https://docs.python.org/3/whatsnew/3.12.html#pep-669-low-impact-monitoring-for-cpython).
The tracer exports to the [Chrome Trace event
format](https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/preview).

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

as a function decorator:

```python
from simple_tracer import traceable

@traceable
def square(x: int) -> int:
    return x**2
```

or as a runnable script:

```shell
simple-tracer -o trace.json.gz -m mymodule
# or
simple-tracer -o trace.json.gz myscript.py
```

## Examples

There are some example scripts in the [`examples`](examples) directory. Some
can be run as a python script, while others are to be launched using the
`simple-tracer` command.

## Limitations

Currently the tracer does not trace built-in dunder methods (e.g. `__add__()`),
due to the way monitoring is implemented. This means that code such as

```python
import numpy as np

x = np.zeros(10)
y = x + x
```

will not record the addition operation as a call to `numpy.ndarray.__add__()`.

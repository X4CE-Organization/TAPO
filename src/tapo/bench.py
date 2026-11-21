"""Built-in micro-benchmarks for the TAPO interpreter."""

from __future__ import annotations

import time

from .interpreter import Interpreter

CASES = [
    (
        "arithmetic",
        "var i = 0\nvar x = 0\nwhile i < 100000 {\n  x = x + (i % 7)\n  i += 1\n}\nx\n",
        100000,
    ),
    (
        "function calls",
        "fn add(a, b) => a + b\nvar i = 0\nvar x = 0\nwhile i < 40000 {\n  x = add(x, i)\n  i += 1\n}\nx\n",
        40000,
    ),
    (
        "method calls",
        "class Counter {\n  var n = 0\n  fn inc(by) { self.n += by; self.n }\n}\nlet c = Counter()\nvar i = 0\nwhile i < 30000 {\n  c.inc(i)\n  i += 1\n}\nc.n\n",
        30000,
    ),
    (
        "collections",
        "let xs = []\nvar i = 0\nwhile i < 20000 {\n  xs.push(i)\n  i += 1\n}\nxs.map(fn(x) => x * 2).sum()\n",
        20000,
    ),
]


def run_bench():
    print("TAPO micro-benchmarks (interpreted, single run)")
    print("%-16s %10s %10s %12s" % ("case", "time", "units", "units/s"))
    for name, source, units in CASES:
        interp = Interpreter()
        started = time.perf_counter()
        interp.run_source(source, "<bench:%s>" % name)
        elapsed = time.perf_counter() - started
        rate = units / elapsed if elapsed else 0.0
        print("%-16s %8.1f ms %10d %12.0f" % (name, elapsed * 1000, units, rate))
    return 0

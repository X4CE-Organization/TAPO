"""Conservative static security audit for TAPO source files."""

from __future__ import annotations

import dataclasses

import tapo.ast as A
from .parser import parse


DANGEROUS = {
    ("fs", "write"): ("high", "writes a file"),
    ("fs", "append"): ("high", "appends to a file"),
    ("fs", "remove"): ("high", "removes a file or directory"),
    ("fs", "mkdir"): ("medium", "creates a directory"),
    ("sys", "exit"): ("high", "terminates the process"),
    ("sys", "chdir"): ("medium", "changes the working directory"),
}

SENSITIVE = {
    "input": ("medium", "reads interactive input"),
    "exit": ("high", "terminates the process"),
}


def _dotted(node):
    if isinstance(node, A.Identifier):
        return node.name
    if isinstance(node, A.Attr):
        base = _dotted(node.obj)
        return (base + "." + node.name) if base else node.name
    return None


def _children(node):
    if dataclasses.is_dataclass(node):
        for field in dataclasses.fields(node):
            value = getattr(node, field.name)
            if dataclasses.is_dataclass(value):
                yield value
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if dataclasses.is_dataclass(item):
                        yield item


def audit_source(source, filename="<audit>"):
    program = parse(source, filename)
    findings = []
    seen = set()

    def add(severity, line, message):
        key = (severity, line, message)
        if key not in seen:
            seen.add(key)
            findings.append((severity, line, message))

    def visit(node):
        if isinstance(node, A.Call):
            name = _dotted(node.callee)
            if name:
                if name in SENSITIVE:
                    add(SENSITIVE[name][0], node.line, "%s: %s" % (name, SENSITIVE[name][1]))
                if name in ("fs.write", "fs.append", "fs.remove", "fs.mkdir", "sys.exit", "sys.chdir"):
                    severity, message = DANGEROUS[(name.split(".")[0], name.split(".")[1])]
                    add(severity, node.line, "%s: %s" % (name, message))
        if isinstance(node, A.Identifier):
            if node.name in SENSITIVE and not isinstance(getattr(node, "parent", None), A.Call):
                pass
        if isinstance(node, A.Import):
            path = node.path
            if not path.startswith("std/") and path not in (
                "math", "json", "fs", "time", "regex", "random", "sys",
                "encoding", "hash", "uuidgen",
            ):
                add("medium", node.line, "imports external module %r" % path)
        if isinstance(node, A.While):
            cond = node.cond
            if isinstance(cond, A.Literal) and cond.value is True:
                add("medium", node.line, "unbounded 'while true' loop")
        if isinstance(node, A.Loop):
            add("medium", node.line, "unbounded 'loop'")
        for child in _children(node):
            visit(child)

    visit(program)
    findings.sort(key=lambda item: (item[1], item[0], item[2]))
    return findings


def audit_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    return audit_source(source, path)

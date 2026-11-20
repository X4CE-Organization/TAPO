"""A conservative source formatter for TAPO.

The formatter is line oriented: it normalises indentation to two spaces per
brace level, trims trailing whitespace, preserves comments and never rewrites
the contents of string literals or block comments.  It is intentionally
conservative rather than a full pretty-printer.
"""

from __future__ import annotations

import os
import re


CONTINUATION_ENDINGS = (
    "|>", "+", "-", "*", "/", "//", "%", "**", "=", "==", "!=", "<", ">",
    "<=", ">=", "&", "|", "^", "<<", ">>", "??", "and", "or", ",", "(", "[",
)
CLOSE_PREFIXES = ("}", ")", "]")
SOFT_CLOSE_PREFIXES = ("else", "elif", "catch", "finally")


def _scan_line(line, state):
    """Update string/comment state and return the brace delta for *line*."""
    i = 0
    delta = 0
    quote = state["quote"]
    triple = state["triple"]
    block_comment = state["block_comment"]
    paren_delta = 0
    while i < len(line):
        ch = line[i]
        if block_comment:
            if line.startswith("=#", i):
                block_comment = False
                i += 2
                continue
            i += 1
            continue
        if triple:
            if line.startswith(triple, i):
                triple = None
                i += 3
                continue
            if ch == "\\":
                i += 2
                continue
            i += 1
            continue
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "#":
            if line.startswith("#=", i):
                block_comment = True
                i += 2
                continue
            break
        if ch in ("'", '"'):
            if line.startswith(ch * 3, i):
                triple = ch * 3
                i += 3
                continue
            quote = ch
            i += 1
            continue
        if ch == "{":
            delta += 1
        elif ch == "}":
            delta -= 1
        elif ch == "(" or ch == "[":
            paren_delta += 1
        elif ch == ")" or ch == "]":
            paren_delta -= 1
        i += 1
    state["quote"] = quote
    state["triple"] = triple
    state["block_comment"] = block_comment
    return delta, paren_delta


def format_source(source):
    """Return *source* with normalised indentation and trailing whitespace."""
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    depth = 0
    continuation = False
    state = {"quote": None, "triple": None, "block_comment": False}
    previous_was_blank = False
    paren_depth = 0

    for raw in lines:
        # Preserve lines that are inside a multi-line string or block comment.
        if state["triple"] or state["block_comment"]:
            out.append(raw.rstrip())
            _, paren_change = _scan_line(raw, state)
            paren_depth = max(0, paren_depth + paren_change)
            previous_was_blank = False
            continue

        text = raw.strip()
        if not text:
            if not previous_was_blank:
                out.append("")
            previous_was_blank = True
            continue
        previous_was_blank = False

        starts_close = text.startswith(CLOSE_PREFIXES)
        soft_close = text.startswith(SOFT_CLOSE_PREFIXES)
        leading = depth - 1 if starts_close else depth
        if leading < 0:
            leading = 0
        if continuation and not starts_close:
            leading += 1
        if text.startswith("|>"):
            leading = depth + 1

        out.append("  " * leading + text)
        delta, paren_change = _scan_line(text, state)
        depth = max(0, depth + delta)
        paren_depth = max(0, paren_depth + paren_change)
        ends_continuation = text.endswith(CONTINUATION_ENDINGS) and not text.startswith("#")
        if ends_continuation and text.endswith(",") and paren_depth == 0:
            # A comma in a match arm or map literal separates entries; it is
            # not a wrapped expression.
            ends_continuation = False
        continuation = ends_continuation

    # Collapse a blank line immediately before EOF and ensure exactly one newline.
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def format_file(path, check=False):
    """Format one file. Returns ``(changed, formatted_text)``."""
    with open(path, "r", encoding="utf-8") as handle:
        original = handle.read()
    formatted = format_source(original)
    changed = formatted != original
    if changed and not check:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(formatted)
    return changed, formatted


def discover(paths, extensions=(".tapo", ".takg")):
    """Yield files to format from paths (directories are walked recursively)."""
    skip = {".git", "build", "dist", "__pycache__", ".venv", "venv", ".idea", ".vscode"}
    for path in paths:
        if os.path.isfile(path):
            yield path
            continue
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d not in skip and not d.startswith("."))
            for name in sorted(files):
                if name.endswith(extensions):
                    yield os.path.join(root, name)

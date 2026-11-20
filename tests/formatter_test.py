"""Unit tests for the TAPO formatter (run directly with Python)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tapo.formatter import format_source
from tapo.parser import parse


def test_indentation_and_idempotence():
    source = "if true {\nprintln(1)\n} else {\nprintln(2)\n}\n"
    formatted = format_source(source)
    assert formatted == "if true {\n  println(1)\n} else {\n  println(2)\n}\n", formatted
    assert format_source(formatted) == formatted


def test_multiline_call_and_comments():
    source = "let x = foo(\n1,\n2\n)\n# keep { this }\n"
    formatted = format_source(source)
    assert formatted == "let x = foo(\n  1,\n  2\n)\n# keep { this }\n", formatted
    parse(formatted, "<formatter-test>")


def test_triple_string_content_is_preserved():
    source = 'let s = """first\n  second\nthird"""\n'
    formatted = format_source(source)
    assert "  second" in formatted
    assert formatted.endswith('\n')


def test_block_comment_braces_are_ignored():
    source = "#= { =#\nif true {\nprintln(1)\n}\n"
    formatted = format_source(source)
    assert formatted == "#= { =#\nif true {\n  println(1)\n}\n", formatted


def test_match_arms_keep_alignment():
    source = "match value {\n  Red => 1,\n  Green => 2\n}\n"
    formatted = format_source(source)
    assert formatted == "match value {\n  Red => 1,\n  Green => 2\n}\n", formatted


def test_trailing_blank_lines_collapse():
    assert format_source("let x = 1\n\n\n") == "let x = 1\n"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("formatter tests passed")

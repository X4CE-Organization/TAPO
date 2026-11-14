"""Error types shared by the TAPO toolchain.

The lexer/parser raise :class:`TapoSyntaxError`; the interpreter raises
:class:`TapoException`, which carries a first-class TAPO error object so that
TAPO code can ``catch`` and inspect it.
"""

from __future__ import annotations


class TapoSyntaxError(Exception):
    """A lexical or syntactic error with source location information."""

    def __init__(self, message, filename="<input>", line=1, col=1, source=None):
        super().__init__(message)
        self.message = message
        self.filename = filename
        self.line = line
        self.col = col
        self.source = source

    def render(self, color=False):
        lines = self.source.splitlines() if self.source else []
        snippet = ""
        if 1 <= self.line <= len(lines):
            text = lines[self.line - 1]
            # Tabs would misalign the caret; show them as a single space.
            display = text.replace("\t", " ")
            pointer = " " * max(0, self.col - 1) + "^"
            snippet = "\n    %s\n    %s" % (display, pointer)
        head = 'File "%s", line %d, column %d' % (
            self.filename,
            self.line,
            self.col,
        )
        body = "SyntaxError: %s" % self.message
        if color:
            return "\x1b[1;31m%s\x1b[0m%s\n\x1b[1;31m%s\x1b[0m" % (
                head,
                snippet,
                body,
            )
        return "%s%s\n%s" % (head, snippet, body)

    def __str__(self):
        return self.render(False)


class TapoException(Exception):
    """A TAPO-level runtime error.

    ``value`` is a TAPO error instance (an instance of ``Error`` or one of its
    subclasses).  ``trace`` is a list of ``(function, filename, line)``
    tuples captured while unwinding, used by the CLI to print a friendly
    stack trace.
    """

    def __init__(self, value, trace=None):
        message = None
        fields = getattr(value, "fields", None)
        if isinstance(fields, dict):
            message = fields.get("message")
        if message is None:
            message = getattr(value, "message", None)
        if message is None:
            message = str(value)
        super().__init__(str(message))
        self.value = value
        self.trace = trace or []

    def add_frame(self, function, filename, line):
        self.trace.append((function, filename, line))


class TapoExit(Exception):
    """Raised by ``exit(code)``; not catchable from TAPO code."""

    def __init__(self, code=0):
        self.code = int(code)
        super().__init__("exit %s" % code)


class TapoBreak(Exception):
    pass


class TapoContinue(Exception):
    pass


class TapoReturn(Exception):
    def __init__(self, value):
        self.value = value
        super().__init__("return")

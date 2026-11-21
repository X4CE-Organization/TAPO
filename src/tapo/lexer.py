"""The TAPO lexer.

TAPO is a small, expression-oriented, object-oriented language.  The lexer is
hand written; it understands:

* integer (decimal/hex/binary/octal) and float literals with ``_`` separators,
* single quoted raw strings and double quoted strings (both may be triple
  quoted), with ``#{...}`` interpolation,
* Unicode identifiers, including a trailing ``?`` (e.g. ``empty?``),
* ``#`` line comments and nestable ``#= ... =#`` block comments.

Newlines are significant only outside ``(`` and ``[``; the parser is
responsible for skipping them where they are not meaningful.
"""

from __future__ import annotations

import string

from .errors import TapoSyntaxError

KEYWORDS = {
    "class",
    "enum",
    "mixin",
    "aspect",
    "fn",
    "let",
    "var",
    "if",
    "else",
    "elif",
    "unless",
    "while",
    "until",
    "for",
    "in",
    "loop",
    "return",
    "break",
    "continue",
    "defer",
    "true",
    "false",
    "nil",
    "and",
    "or",
    "not",
    "is",
    "match",
    "try",
    "catch",
    "finally",
    "raise",
    "yield",
    "import",
    "export",
    "as",
    "with",
    "use",
    "static",
    "get",
    "set",
    "self",
    "super",
    "before",
    "after",
    "around",
}

# Longest first so that greedy matching works.
OPERATORS = [
    "...",
    "??=",
    "**=",
    "//=",
    "<<=",
    ">>=",
    "|>",
    "?.",
    "??",
    "||",
    "&&",
    "==",
    "!=",
    "<=",
    ">=",
    "<<",
    ">>",
    "**",
    "//",
    "+=",
    "-=",
    "*=",
    "/=",
    "%=",
    "^=",
    "&=",
    "|=",
    "=>",
    "..",
    "=",
    "+",
    "-",
    "*",
    "/",
    "%",
    "<",
    ">",
    "!",
    "~",
    "&",
    "|",
    "^",
    ",",
    ";",
    ":",
    ".",
    "(",
    ")",
    "[",
    "]",
    "{",
    "}",
    "@",
]

_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "#": "#",
}


class Token:
    __slots__ = ("type", "value", "line", "col", "file")

    def __init__(self, type_, value, line, col, file):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col
        self.file = file

    def __repr__(self):
        if self.type == "STRING":
            return "Token(STRING, %r, %d:%d)" % (self.value, self.line, self.col)
        return "Token(%s, %r, %d:%d)" % (self.type, self.value, self.line, self.col)


class Lexer:
    def __init__(self, source, filename="<input>"):
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.col = 1
        self.length = len(source)
        self.depth = 0  # legacy bracket depth, kept for diagnostics
        self.brackets = []  # stack of ( [ { delimiters
        self.tokens = []

    # ------------------------------------------------------------------
    # character helpers
    # ------------------------------------------------------------------
    def peek(self, offset=0):
        i = self.pos + offset
        if i < self.length:
            return self.source[i]
        return ""

    def advance(self):
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def error(self, message, line=None, col=None):
        raise TapoSyntaxError(
            message,
            self.filename,
            line or self.line,
            col or self.col,
            self.source,
        )

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------
    def tokenize(self):
        while self.pos < self.length:
            ch = self.peek()
            if ch in " \t\r":
                self.advance()
                continue
            if ch == "\n":
                line, col = self.line, self.col
                self.advance()
                # Newlines are insignificant directly inside parentheses and
                # list literals, but a brace block nested inside a call must
                # keep its newlines (e.g. test("x", fn() { ... })).
                suppress = bool(self.brackets) and self.brackets[-1] in ("(", "[")
                if not suppress:
                    if not self.tokens or self.tokens[-1].type != "NEWLINE":
                        self.tokens.append(Token("NEWLINE", "\n", line, col, self.filename))
                continue
            if ch == "#":
                if self.peek(1) == "=":
                    self.skip_block_comment()
                elif self.peek(1) == "{":
                    # A stray interpolation outside a string is an error; let
                    # the operator scanner report it below.
                    self.error("unexpected interpolation outside of a string")
                else:
                    while self.pos < self.length and self.peek() != "\n":
                        self.advance()
                continue
            if ch.isdigit() or (ch == "." and self.peek(1).isdigit()):
                self.scan_number()
                continue
            if ch in "\"'":
                self.scan_string()
                continue
            if self.is_ident_start(ch):
                self.scan_identifier()
                continue
            if self.scan_operator():
                continue
            self.error("unexpected character %r" % ch)
        self.tokens.append(Token("EOF", None, self.line, self.col, self.filename))
        return self.tokens

    # ------------------------------------------------------------------
    # comments
    # ------------------------------------------------------------------
    def skip_block_comment(self):
        start_line, start_col = self.line, self.col
        nesting = 0
        while self.pos < self.length:
            if self.peek() == "#" and self.peek(1) == "=":
                self.advance()
                self.advance()
                nesting += 1
            elif self.peek() == "=" and self.peek(1) == "#":
                self.advance()
                self.advance()
                nesting -= 1
                if nesting == 0:
                    return
            else:
                self.advance()
        self.error("unterminated block comment", start_line, start_col)

    # ------------------------------------------------------------------
    # numbers
    # ------------------------------------------------------------------
    def scan_number(self):
        start_line, start_col = self.line, self.col
        start = self.pos
        is_float = False

        if self.peek() == "0" and self.peek(1) and self.peek(1) in "xX":
            self.advance()
            self.advance()
            digits = self.consume_digits("0123456789abcdefABCDEF")
            if not digits:
                self.error("malformed hexadecimal literal", start_line, start_col)
            value = int(digits.replace("_", ""), 16)
            self.tokens.append(
                Token("NUMBER", value, start_line, start_col, self.filename)
            )
            return
        if self.peek() == "0" and self.peek(1) and self.peek(1) in "bB":
            self.advance()
            self.advance()
            digits = self.consume_digits("01")
            if not digits:
                self.error("malformed binary literal", start_line, start_col)
            value = int(digits.replace("_", ""), 2)
            self.tokens.append(
                Token("NUMBER", value, start_line, start_col, self.filename)
            )
            return
        if self.peek() == "0" and self.peek(1) and self.peek(1) in "oO":
            self.advance()
            self.advance()
            digits = self.consume_digits("01234567")
            if not digits:
                self.error("malformed octal literal", start_line, start_col)
            value = int(digits.replace("_", ""), 8)
            self.tokens.append(
                Token("NUMBER", value, start_line, start_col, self.filename)
            )
            return

        digits = self.consume_digits(string.digits)
        # A dot only starts a fraction when it is not part of a range and is
        # followed by a digit.
        if (
            self.peek() == "."
            and self.peek(1) != "."
            and self.peek(1).isdigit()
        ):
            is_float = True
            self.advance()
            digits += "." + self.consume_digits(string.digits)
        if self.peek() and self.peek() in "eE":
            save = self.pos
            save_line, save_col = self.line, self.col
            self.advance()
            sign = ""
            if self.peek() and self.peek() in "+-":
                sign = self.advance()
            exp = self.consume_digits(string.digits)
            if not exp:
                # Not an exponent, e.g. 1.toString(); rewind.
                self.pos = save
                self.line, self.col = save_line, save_col
            else:
                is_float = True
                digits += "e" + sign + exp
        text = digits.replace("_", "")
        if text.startswith("."):
            text = "0" + text
        try:
            value = float(text) if is_float else int(text)
        except ValueError:
            self.error("malformed number literal %r" % self.source[start : self.pos])
        self.tokens.append(Token("NUMBER", value, start_line, start_col, self.filename))

    def consume_digits(self, allowed):
        out = []
        while self.pos < self.length:
            ch = self.peek()
            if ch == "_" and out:
                self.advance()
                continue
            if ch in allowed:
                out.append(self.advance())
            else:
                break
        return "".join(out)

    # ------------------------------------------------------------------
    # identifiers / keywords
    # ------------------------------------------------------------------
    @staticmethod
    def is_ident_start(ch):
        return bool(ch) and (ch == "_" or ch.isalpha() or ord(ch) > 127)

    @staticmethod
    def is_ident_char(ch):
        return bool(ch) and (ch == "_" or ch.isalnum() or ord(ch) > 127)

    def scan_identifier(self):
        line, col = self.line, self.col
        chars = [self.advance()]
        while self.pos < self.length and self.is_ident_char(self.peek()):
            chars.append(self.advance())
        # Predicate-style names: empty?, divisible_by?
        if self.peek() == "?" and (not self.peek(1) or self.peek(1) not in "?=."):
            chars.append(self.advance())
        # Bang-style names: merge!, sort!
        elif self.peek() == "!" and (not self.peek(1) or self.peek(1) != "="):
            chars.append(self.advance())
        name = "".join(chars)
        if name in KEYWORDS:
            self.tokens.append(Token("KEYWORD", name, line, col, self.filename))
        else:
            self.tokens.append(Token("IDENT", name, line, col, self.filename))

    # ------------------------------------------------------------------
    # strings
    # ------------------------------------------------------------------
    def scan_string(self):
        line, col = self.line, self.col
        quote = self.advance()
        raw = quote == "'"
        triple = self.peek() == quote and self.peek(1) == quote
        if triple:
            self.advance()
            self.advance()
        parts = []
        buf = []

        def flush():
            if buf:
                parts.append((True, "".join(buf)))
                del buf[:]

        while True:
            if self.pos >= self.length:
                self.error("unterminated string literal", line, col)
            if triple:
                if self.peek() == quote and self.peek(1) == quote and self.peek(2) == quote:
                    self.advance()
                    self.advance()
                    self.advance()
                    break
            else:
                if self.peek() == quote:
                    self.advance()
                    break
            ch = self.peek()
            if ch == "\\" and not (raw and (not self.peek(1) or self.peek(1) not in "'\\")):
                self.advance()
                esc_line, esc_col = self.line, self.col
                esc = self.advance()
                if esc in _ESCAPES:
                    buf.append(_ESCAPES[esc])
                elif esc == "u":
                    buf.append(self.scan_unicode_escape(esc_line, esc_col))
                elif esc == "x":
                    buf.append(self.scan_hex_escape(esc_line, esc_col))
                elif esc == "\n":
                    # line continuation
                    pass
                else:
                    self.error(
                        "unknown escape sequence '\\%s'" % esc, esc_line, esc_col
                    )
                continue
            if not raw and ch == "#" and self.peek(1) == "{":
                self.advance()
                self.advance()
                flush()
                parts.append((False, self.scan_interpolation(line, col)))
                continue
            buf.append(self.advance())
        flush()
        if not parts:
            parts = [(True, "")]
        self.tokens.append(Token("STRING", parts, line, col, self.filename))

    def scan_unicode_escape(self, line, col):
        digits = ""
        if self.peek() == "{":
            self.advance()
            while self.peek() != "}" and self.peek() != "":
                digits += self.advance()
            if self.peek() != "}":
                self.error("unterminated \\u{...} escape", line, col)
            self.advance()
        else:
            for _ in range(4):
                if not self.peek():
                    self.error("incomplete \\u escape", line, col)
                digits += self.advance()
        try:
            return chr(int(digits, 16))
        except (ValueError, OverflowError):
            self.error("invalid unicode escape %r" % digits, line, col)

    def scan_hex_escape(self, line, col):
        digits = ""
        for _ in range(2):
            if not self.peek():
                self.error("incomplete \\x escape", line, col)
            digits += self.advance()
        try:
            return chr(int(digits, 16))
        except ValueError:
            self.error("invalid hex escape %r" % digits, line, col)

    def scan_interpolation(self, string_line, string_col):
        """Consume the source inside ``#{ ... }`` and return it as a string."""
        start = self.pos
        depth = 1
        while self.pos < self.length:
            ch = self.peek()
            if ch == "{":
                depth += 1
                self.advance()
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    src = self.source[start : self.pos]
                    self.advance()
                    return src
                self.advance()
            elif ch in "\"'":
                # Skip over nested string literals so braces inside them do
                # not affect the interpolation nesting.
                quote = self.advance()
                while self.pos < self.length:
                    c = self.peek()
                    if c == "\\":
                        self.advance()
                        if self.pos < self.length:
                            self.advance()
                    elif c == quote:
                        self.advance()
                        break
                    else:
                        self.advance()
            else:
                self.advance()
        self.error("unterminated string interpolation", string_line, string_col)

    # ------------------------------------------------------------------
    # operators
    # ------------------------------------------------------------------
    def scan_operator(self):
        for op in OPERATORS:
            if self.source.startswith(op, self.pos):
                line, col = self.line, self.col
                for _ in op:
                    self.advance()
                if op in "([{":
                    self.depth += 1
                    self.brackets.append(op)
                elif op in ")]}":
                    self.depth = max(0, self.depth - 1)
                    if self.brackets:
                        opening = {"(": ")", "[": "]", "{": "}"}.get(self.brackets[-1])
                        if opening == op:
                            self.brackets.pop()
                self.tokens.append(
                    Token("OP", op, line, col, self.filename)
                )
                return True
        return False


def tokenize(source, filename="<input>"):
    return Lexer(source, filename).tokenize()

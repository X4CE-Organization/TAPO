"""Recursive-descent + Pratt parser for TAPO."""

from __future__ import annotations

from . import ast as A
from .errors import TapoSyntaxError
from .lexer import Lexer, tokenize

# Binary operator precedence.  Larger binds tighter.
PRECEDENCE = {
    "??": 3,
    "or": 4,
    "||": 4,
    "and": 5,
    "&&": 5,
    "==": 6,
    "!=": 6,
    "<": 7,
    "<=": 7,
    ">": 7,
    ">=": 7,
    "in": 7,
    "is": 7,
    "..": 8,
    "...": 8,
    "|": 9,
    "^": 10,
    "&": 11,
    "<<": 12,
    ">>": 12,
    "+": 13,
    "-": 13,
    "*": 14,
    "/": 14,
    "//": 14,
    "%": 14,
    "**": 15,
}

RIGHT_ASSOC = {"**", "??"}

ASSIGN_OPS = {
    "=",
    "+=",
    "-=",
    "*=",
    "/=",
    "//=",
    "%=",
    "**=",
    "|=",
    "&=",
    "^=",
    "<<=",
    ">>=",
    "??=",
}

METHOD_OPERATORS = {
    "+",
    "-",
    "*",
    "/",
    "//",
    "%",
    "**",
    "==",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "&",
    "|",
    "^",
    "<<",
    ">>",
    "~",
}

PIPE_PREC = 2
ASSIGN_PREC = 1
UNARY_PREC = 16


class Parser:
    def __init__(self, tokens, filename="<input>", source=None):
        self.tokens = tokens
        self.filename = filename
        self.source = source
        self.pos = 0
        self._saw_placeholder = False

    # ------------------------------------------------------------------
    # token helpers
    # ------------------------------------------------------------------
    @property
    def current(self):
        return self.tokens[self.pos]

    def peek(self, offset=1):
        i = self.pos + offset
        if i < len(self.tokens):
            return self.tokens[i]
        return self.tokens[-1]

    def check(self, type_, value=None):
        tok = self.current
        if tok.type != type_:
            return False
        return value is None or tok.value == value

    def check_op(self, value):
        return self.current.type == "OP" and self.current.value == value

    def check_kw(self, value):
        return self.current.type == "KEYWORD" and self.current.value == value

    def advance(self):
        tok = self.current
        self.pos += 1
        return tok

    def match_op(self, value):
        if self.check_op(value):
            self.advance()
            return True
        return False

    def match_kw(self, value):
        if self.check_kw(value):
            self.advance()
            return True
        return False

    def expect_op(self, value, what=None):
        if not self.check_op(value):
            self.error("expected %r" % (what or value))
        return self.advance()

    def expect_kw(self, value):
        if not self.check_kw(value):
            self.error("expected keyword %r" % value)
        return self.advance()

    def expect_ident(self, what="identifier"):
        tok = self.current
        if tok.type != "IDENT":
            self.error("expected %s" % what)
        self.advance()
        return tok.value

    def error(self, message, tok=None):
        tok = tok or self.current
        raise TapoSyntaxError(
            message, self.filename, tok.line, tok.col, self.source
        )

    def skip_newlines(self):
        while self.current.type == "NEWLINE":
            self.advance()

    def skip_separators(self):
        while self.current.type == "NEWLINE" or self.check_op(";"):
            self.advance()

    # ------------------------------------------------------------------
    # entry points
    # ------------------------------------------------------------------
    def parse_program(self):
        stmts = []
        self.skip_separators()
        while not self.check("EOF"):
            stmts.append(self.parse_statement())
            if self.check("EOF"):
                break
            if self.check_op(";"):
                self.skip_separators()
            elif self.current.type == "NEWLINE":
                self.skip_separators()
            elif self.check_op("}"):
                self.error("unexpected '}'")
            else:
                self.error("expected a newline or ';' between statements")
        return A.Block(stmts, 1, 1)

    def parse_expression_only(self):
        self.skip_newlines()
        expr = self.parse_expression(0)
        self.skip_newlines()
        if not self.check("EOF"):
            self.error("unexpected token after expression")
        return expr

    # ------------------------------------------------------------------
    # statements
    # ------------------------------------------------------------------
    def parse_statement(self):
        tok = self.current
        if tok.type == "KEYWORD":
            kw = tok.value
            if kw == "class":
                return self.parse_class()
            if kw == "mixin":
                return self.parse_mixin()
            if kw == "aspect":
                return self.parse_aspect()
            if kw == "fn":
                nxt = self.peek()
                if nxt.type == "IDENT":
                    after = self.peek(2)
                    if after.type == "OP" and after.value == "(":
                        return self.parse_function_decl()
                elif (
                    nxt.type == "OP"
                    and nxt.value in METHOD_OPERATORS
                    and self.peek(2).type == "OP"
                    and self.peek(2).value == "("
                ):
                    return self.parse_function_decl(allow_operator=True)
                return self.parse_expression(0)
            if kw in ("let", "var"):
                return self.parse_var_decl()
            if kw == "import":
                return self.parse_import()
            if kw == "export":
                return self.parse_export()
            if kw == "return":
                return self.parse_return()
            if kw == "break":
                self.advance()
                return A.Break(tok.line, tok.col)
            if kw == "continue":
                self.advance()
                return A.Continue(tok.line, tok.col)
            if kw == "raise":
                self.advance()
                value = self.parse_expression(0)
                return A.Raise(value, tok.line, tok.col)
            if kw == "while":
                return self.parse_while()
            if kw == "until":
                return self.parse_while(is_until=True)
            if kw == "for":
                return self.parse_for()
            if kw == "loop":
                self.advance()
                body = self.parse_block()
                return A.Loop(body, tok.line, tok.col)
            if kw == "use":
                self.error("'use' is only allowed inside a class or mixin body")
        return self.parse_expression(0)

    def parse_block(self):
        start = self.expect_op("{")
        stmts = []
        self.skip_separators()
        while not self.check_op("}"):
            if self.check("EOF"):
                self.error("unterminated block; expected '}'", start)
            stmts.append(self.parse_statement())
            if self.check_op("}"):
                break
            if self.check_op(";"):
                self.skip_separators()
            elif self.current.type == "NEWLINE":
                self.skip_separators()
            elif self.check("EOF"):
                self.error("unterminated block; expected '}'", start)
            else:
                self.error("expected a newline, ';' or '}' after statement")
        self.expect_op("}")
        return A.Block(stmts, start.line, start.col)

    def parse_var_decl(self, require_value=False):
        start = self.advance()  # let / var
        kind = start.value
        decls = []
        while True:
            pattern = self.parse_pattern()
            value = None
            if self.match_op("="):
                value = self.parse_expression(0)
            elif kind == "let":
                self.error("'let' declarations require a value", start)
            else:
                value = A.Literal(None, start.line, start.col)
            decls.append(
                A.VarDecl(kind, pattern, value, pattern.line or start.line, pattern.col or start.col)
            )
            if self.check_op(","):
                self.advance()
                self.skip_newlines()
                continue
            break
        if len(decls) == 1:
            return decls[0]
        return A.Block(decls, start.line, start.col)

    def parse_function_decl(self, allow_operator=False):
        start = self.expect_kw("fn")
        if self.current.type == "IDENT":
            name = self.advance().value
        elif allow_operator and self.current.type == "OP" and self.current.value in METHOD_OPERATORS:
            name = self.advance().value
        else:
            self.error("expected a function name")
        params = self.parse_params()
        if self.match_op("=>"):
            expr = self.parse_expression(0)
            body = A.Block([expr], expr.line, expr.col)
        else:
            body = self.parse_block()
        return A.FnDecl(name, params, body, False, start.line, start.col)

    def parse_return(self):
        start = self.expect_kw("return")
        if (
            self.current.type == "NEWLINE"
            or self.check_op(";")
            or self.check_op("}")
            or self.check("EOF")
        ):
            return A.Return(None, start.line, start.col)
        value = self.parse_expression(0)
        return A.Return(value, start.line, start.col)

    def parse_import(self):
        start = self.expect_kw("import")
        if self.current.type != "STRING":
            self.error("import path must be a string literal")
        parts = self.advance().value
        if len(parts) != 1 or not parts[0][0]:
            self.error("import path must not use interpolation")
        path = parts[0][1]
        alias = None
        if self.match_kw("as"):
            alias = self.expect_ident("module alias")
        return A.Import(path, alias, start.line, start.col)

    def parse_export(self):
        start = self.expect_kw("export")
        tok = self.current
        if tok.type == "KEYWORD" and tok.value in (
            "class",
            "mixin",
            "aspect",
            "fn",
            "let",
            "var",
        ):
            decl = self.parse_statement()
            return A.Export(decl, start.line, start.col)
        if tok.type == "IDENT":
            name = self.advance()
            return A.Export(
                A.Identifier(name.value, name.line, name.col), start.line, start.col
            )
        self.error("expected a declaration or name after 'export'")

    def parse_while(self, is_until=False):
        start = self.advance()
        cond = self.parse_expression(0)
        body = self.parse_block()
        return A.While(cond, body, is_until, start.line, start.col)

    def parse_for(self):
        start = self.expect_kw("for")
        pattern = self.parse_pattern()
        self.expect_kw("in")
        iterable = self.parse_expression(0)
        body = self.parse_block()
        return A.For(pattern, iterable, body, start.line, start.col)

    # ------------------------------------------------------------------
    # classes, mixins and aspects
    # ------------------------------------------------------------------
    def parse_class(self):
        start = self.expect_kw("class")
        name = self.expect_ident("class name")
        superclass = None
        if self.match_op("<"):
            superclass = self.parse_expression(0)
        mixins = []
        if self.match_kw("with"):
            while True:
                mixins.append(self.parse_expression(0))
                if not self.match_op(","):
                    break
                self.skip_newlines()
        members = self.parse_members()
        return A.ClassDecl(name, superclass, mixins, members, start.line, start.col)

    def parse_mixin(self):
        start = self.expect_kw("mixin")
        name = self.expect_ident("mixin name")
        members = self.parse_members(allow_static=True)
        return A.MixinDecl(name, members, start.line, start.col)

    def parse_members(self, allow_static=True):
        self.expect_op("{")
        members = []
        self.skip_separators()
        while not self.check_op("}"):
            if self.check("EOF"):
                self.error("unterminated class body")
            tok = self.current
            if tok.type == "KEYWORD" and tok.value in ("var", "let"):
                members.extend(self.parse_field_decls())
            elif tok.type == "KEYWORD" and tok.value == "fn":
                members.append(self.parse_method_decl())
            elif tok.type == "IDENT" and self.peek().type == "OP" and self.peek().value == "(":
                # Sugar: init(name) { ... } is equivalent to fn init(name) { ... }
                members.append(self.parse_method_decl())
            elif tok.type == "KEYWORD" and tok.value == "static" and allow_static:
                self.advance()
                if not self.check_kw("fn"):
                    self.error("only 'static fn' is supported inside a class")
                members.append(self.parse_method_decl(static=True))
            elif tok.type == "KEYWORD" and tok.value in ("get", "set") and self.peek().type == "OP" and self.peek().value == "(":
                # 'get' and 'set' are also the names of the index protocol
                # methods, so allow bare get(i) { ... } / set(i, v) { ... }.
                members.append(self.parse_method_decl())
            elif tok.type == "KEYWORD" and tok.value == "get":
                members.append(self.parse_getter())
            elif tok.type == "KEYWORD" and tok.value == "set":
                members.append(self.parse_setter())
            elif tok.type == "KEYWORD" and tok.value == "use":
                self.advance()
                expr = self.parse_expression(0)
                members.append(A.UseAspect(expr, tok.line, tok.col))
            else:
                self.error("unexpected %r in class body" % (tok.value or tok.type))
            if self.check_op("}"):
                break
            if self.check_op(";"):
                self.skip_separators()
            elif self.current.type == "NEWLINE":
                self.skip_separators()
            else:
                self.error("expected a newline, ';' or '}' after class member")
        self.expect_op("}")
        return members

    def parse_field_decls(self):
        decls = []
        start = self.advance()  # var/let
        kind = start.value
        while True:
            name_tok = self.current
            name = self.expect_ident("field name")
            value = A.Literal(None, name_tok.line, name_tok.col)
            if self.match_op("="):
                value = self.parse_expression(0)
            decls.append(
                A.VarDecl(
                    kind,
                    A.PVar(name, name_tok.line, name_tok.col),
                    value,
                    name_tok.line,
                    name_tok.col,
                )
            )
            if not self.check_op(","):
                break
            self.advance()
            self.skip_newlines()
        return decls

    def parse_method_decl(self, static=False):
        if self.check_kw("fn"):
            start = self.advance()
        else:
            start = self.current
        if self.current.type == "IDENT":
            name = self.advance().value
        elif self.current.type == "KEYWORD" and self.current.value in ("get", "set"):
            name = self.advance().value
        elif self.current.type == "OP" and self.current.value in METHOD_OPERATORS:
            name = self.advance().value
        else:
            self.error("expected a method name")
        params = self.parse_params()
        if self.match_op("=>"):
            expr = self.parse_expression(0)
            body = A.Block([expr], expr.line, expr.col)
        else:
            body = self.parse_block()
        return A.FnDecl(name, params, body, static, start.line, start.col)

    def parse_getter(self):
        start = self.expect_kw("get")
        name = self.expect_ident("property name")
        if self.match_op("=>"):
            expr = self.parse_expression(0)
            body = A.Block([expr], expr.line, expr.col)
        else:
            body = self.parse_block()
        return A.GetterDecl(name, body, start.line, start.col)

    def parse_setter(self):
        start = self.expect_kw("set")
        name = self.expect_ident("property name")
        self.expect_op("(")
        self.skip_newlines()
        param = self.parse_pattern()
        self.skip_newlines()
        self.expect_op(")")
        body = self.parse_block()
        return A.SetterDecl(
            name, A.Param(param, None, False, param.line, param.col), body, start.line, start.col
        )

    def parse_aspect(self):
        start = self.expect_kw("aspect")
        name = self.expect_ident("aspect name")
        self.expect_op("{")
        advices = []
        self.skip_separators()
        while not self.check_op("}"):
            tok = self.current
            if tok.type != "KEYWORD" or tok.value not in ("before", "after", "around"):
                self.error("expected 'before', 'after' or 'around' in aspect body")
            kind = self.advance().value
            if self.current.type == "IDENT":
                selector = self.advance().value
            elif self.check_op("*"):
                self.advance()
                selector = "*"
            else:
                self.error("expected a method name or '*' as aspect selector")
            params = self.parse_params()
            body = self.parse_block()
            advices.append(
                A.Advice(kind, selector, params, body, tok.line, tok.col)
            )
            if self.check_op("}"):
                break
            if self.check_op(";"):
                self.skip_separators()
            elif self.current.type == "NEWLINE":
                self.skip_separators()
            else:
                self.error("expected a newline or ';' after advice")
        self.expect_op("}")
        return A.AspectDecl(name, advices, start.line, start.col)

    # ------------------------------------------------------------------
    # expressions
    # ------------------------------------------------------------------
    def parse_expression(self, min_prec=0):
        left = self.parse_prefix()
        left = self.parse_postfix(left)

        while True:
            tok = self.current

            # A pipe may start a continuation line:
            #   xs
            #     |> _.map(...)
            #     |> _.sum()
            if tok.type == "NEWLINE":
                saved_pos = self.pos
                self.skip_newlines()
                if self.check_op("|>"):
                    tok = self.current
                else:
                    self.pos = saved_pos
                    break

            # assignment (lowest precedence, right associative)
            if tok.type == "OP" and tok.value in ASSIGN_OPS:
                if min_prec > ASSIGN_PREC:
                    break
                self.advance()
                self.skip_newlines()
                value = self.parse_expression(ASSIGN_PREC)
                if not isinstance(left, (A.Identifier, A.Attr, A.Index)):
                    self.error("invalid assignment target", tok)
                left = A.Assign(left, tok.value, value, tok.line, tok.col)
                continue

            # pipe
            if tok.type == "OP" and tok.value == "|>":
                if PIPE_PREC < min_prec:
                    break
                self.advance()
                self.skip_newlines()
                saved = self._saw_placeholder
                self._saw_placeholder = False
                rhs = self.parse_prefix()
                rhs = self.parse_postfix(rhs)
                has_ph = self._saw_placeholder
                self._saw_placeholder = saved or has_ph
                left = A.Pipe(left, rhs, has_ph, tok.line, tok.col)
                continue

            if tok.type == "OP" and tok.value in PRECEDENCE:
                op = tok.value
            elif tok.type == "KEYWORD" and tok.value in PRECEDENCE:
                op = tok.value
            else:
                break
            prec = PRECEDENCE[op]
            if prec < min_prec:
                break
            self.advance()
            self.skip_newlines()
            next_min = prec if op in RIGHT_ASSOC else prec + 1
            right = self.parse_expression(next_min)
            left = A.Binary(op, left, right, tok.line, tok.col)
        return left

    def parse_prefix(self):
        tok = self.current
        if tok.type == "NUMBER":
            self.advance()
            return A.Literal(tok.value, tok.line, tok.col)
        if tok.type == "STRING":
            self.advance()
            return self.build_string(tok)
        if tok.type == "IDENT":
            self.advance()
            if tok.value == "_":
                self._saw_placeholder = True
                return A.Placeholder(tok.line, tok.col)
            return A.Identifier(tok.value, tok.line, tok.col)
        if tok.type == "KEYWORD":
            kw = tok.value
            if kw == "true":
                self.advance()
                return A.Literal(True, tok.line, tok.col)
            if kw == "false":
                self.advance()
                return A.Literal(False, tok.line, tok.col)
            if kw == "nil":
                self.advance()
                return A.Literal(None, tok.line, tok.col)
            if kw == "self":
                self.advance()
                return A.SelfExpr(tok.line, tok.col)
            if kw == "super":
                self.advance()
                method = None
                if self.check_op("."):
                    self.advance()
                    method = self.parse_attr_name()
                return A.SuperExpr(method, tok.line, tok.col)
            if kw == "fn":
                return self.parse_lambda()
            if kw in ("if", "unless"):
                return self.parse_if()
            if kw == "match":
                return self.parse_match()
            if kw == "try":
                return self.parse_try()
            if kw == "not":
                self.advance()
                operand = self.parse_expression(6)
                return A.Unary("not", operand, tok.line, tok.col)
        if tok.type == "OP":
            if tok.value in ("-", "+", "!", "~"):
                self.advance()
                operand = self.parse_expression(UNARY_PREC)
                return A.Unary(tok.value, operand, tok.line, tok.col)
            if tok.value == "(":
                self.advance()
                self.skip_newlines()
                expr = self.parse_expression(0)
                self.skip_newlines()
                self.expect_op(")")
                return expr
            if tok.value == "[":
                return self.parse_list_literal()
            if tok.value == "{":
                return self.parse_map_literal()
        self.error("unexpected token %r" % (tok.value if tok.value is not None else tok.type))

    def parse_postfix(self, left):
        while True:
            tok = self.current
            if tok.type != "OP":
                break
            if tok.value == "(":
                args = self.parse_call_args()
                left = A.Call(left, args, tok.line, tok.col)
            elif tok.value == "[":
                self.advance()
                self.skip_newlines()
                index = self.parse_expression(0)
                self.skip_newlines()
                self.expect_op("]")
                left = A.Index(left, index, tok.line, tok.col)
            elif tok.value in (".", "?."):
                self.advance()
                name = self.parse_attr_name()
                left = A.Attr(left, name, tok.value == "?.", tok.line, tok.col)
            else:
                break
        return left

    def parse_attr_name(self):
        tok = self.current
        if tok.type in ("IDENT", "KEYWORD"):
            self.advance()
            return tok.value
        self.error("expected an attribute name")

    def parse_call_args(self):
        self.expect_op("(")
        args = []
        self.skip_newlines()
        while not self.check_op(")"):
            if self.check_op("..."):
                start = self.advance()
                expr = self.parse_expression(0)
                args.append(A.Splat(expr, start.line, start.col))
            else:
                args.append(self.parse_expression(0))
            self.skip_newlines()
            if self.check_op(","):
                self.advance()
                self.skip_newlines()
                continue
            break
        self.skip_newlines()
        self.expect_op(")")
        return args

    def parse_list_literal(self):
        start = self.expect_op("[")
        items = []
        self.skip_newlines()
        while not self.check_op("]"):
            if self.check_op("..."):
                s = self.advance()
                items.append(A.Splat(self.parse_expression(0), s.line, s.col))
            else:
                items.append(self.parse_expression(0))
            self.skip_newlines()
            if self.check_op(","):
                self.advance()
                self.skip_newlines()
                continue
            break
        self.skip_newlines()
        self.expect_op("]")
        return A.ListLit(items, start.line, start.col)

    def parse_map_literal(self):
        start = self.expect_op("{")
        pairs = []
        self.skip_newlines()
        while not self.check_op("}"):
            key = self.parse_map_key()
            self.expect_op(":")
            value = self.parse_expression(0)
            pairs.append((key, value))
            self.skip_newlines()
            if self.check_op(","):
                self.advance()
                self.skip_newlines()
                continue
            break
        self.skip_newlines()
        self.expect_op("}")
        return A.MapLit(pairs, start.line, start.col)

    def parse_map_key(self):
        tok = self.current
        if tok.type in ("IDENT", "KEYWORD") and self.peek().type == "OP" and self.peek().value == ":":
            self.advance()
            return A.Literal(tok.value, tok.line, tok.col)
        return self.parse_expression(0)

    def parse_lambda(self):
        start = self.expect_kw("fn")
        params = self.parse_params()
        if self.match_op("=>"):
            expr = self.parse_expression(0)
            body = A.Block([expr], expr.line, expr.col)
        else:
            body = self.parse_block()
        return A.Lambda(params, body, "<lambda>", start.line, start.col)

    def parse_params(self):
        self.expect_op("(")
        params = []
        self.skip_newlines()
        while not self.check_op(")"):
            start = self.current
            is_rest = False
            if self.check_op("..."):
                self.advance()
                is_rest = True
            if self.check_kw("self"):
                st = self.advance()
                pattern = A.PVar("self", st.line, st.col)
            else:
                pattern = self.parse_pattern()
            default = None
            if not is_rest and self.match_op("="):
                default = self.parse_expression(0)
            params.append(
                A.Param(pattern, default, is_rest, start.line, start.col)
            )
            if is_rest:
                self.skip_newlines()
                if self.check_op(","):
                    self.error("rest parameter must be last")
                break
            self.skip_newlines()
            if self.check_op(","):
                self.advance()
                self.skip_newlines()
                continue
            break
        self.skip_newlines()
        self.expect_op(")")
        return params

    def parse_if(self):
        start = self.advance()
        negate = start.value == "unless"
        cond = self.parse_expression(0)
        if negate:
            cond = A.Unary("not", cond, start.line, start.col)
        then = self.parse_block()
        otherwise = None
        if self.match_kw("elif"):
            nested = self.parse_if_after_keyword(start)
            otherwise = A.Block([nested], nested.line, nested.col)
        elif self.match_kw("else"):
            if self.check_kw("if"):
                nested = self.parse_if()
                otherwise = A.Block([nested], nested.line, nested.col)
            else:
                otherwise = self.parse_block()
        return A.If(cond, then, otherwise, start.line, start.col)

    def parse_if_after_keyword(self, start):
        # 'elif' has already been consumed; parse condition + block + tail.
        cond = self.parse_expression(0)
        then = self.parse_block()
        otherwise = None
        if self.match_kw("elif"):
            nested = self.parse_if_after_keyword(start)
            otherwise = A.Block([nested], nested.line, nested.col)
        elif self.match_kw("else"):
            if self.check_kw("if"):
                nested = self.parse_if()
                otherwise = A.Block([nested], nested.line, nested.col)
            else:
                otherwise = self.parse_block()
        return A.If(cond, then, otherwise, start.line, start.col)

    def parse_try(self):
        start = self.expect_kw("try")
        body = self.parse_block()
        catch_name = None
        catch_body = None
        finally_body = None
        if self.match_kw("catch"):
            if self.current.type == "IDENT":
                catch_name = self.advance().value
            catch_body = self.parse_block()
        if self.match_kw("finally"):
            finally_body = self.parse_block()
        if catch_body is None and finally_body is None:
            self.error("'try' needs a 'catch' or 'finally' block")
        return A.Try(body, catch_name, catch_body, finally_body, start.line, start.col)

    def parse_match(self):
        start = self.expect_kw("match")
        subject = self.parse_expression(0)
        self.expect_op("{")
        arms = []
        self.skip_separators()
        while not self.check_op("}"):
            if self.check("EOF"):
                self.error("unterminated match block", start)
            arm_tok = self.current
            if self.check_kw("else"):
                self.advance()
                pattern = A.PWildcard(arm_tok.line, arm_tok.col)
            else:
                pattern = self.parse_pattern()
            guard = None
            if self.match_kw("if"):
                guard = self.parse_expression(0)
            self.expect_op("=>")
            self.skip_newlines()
            if self.check_op("{"):
                body = self.parse_block()
            else:
                expr = self.parse_expression(0)
                body = A.Block([expr], expr.line, expr.col)
            arms.append(A.MatchArm(pattern, guard, body, arm_tok.line, arm_tok.col))
            if self.check_op("}"):
                break
            if self.check_op(",") or self.check_op(";"):
                self.advance()
                self.skip_separators()
            elif self.current.type == "NEWLINE":
                self.skip_separators()
            else:
                self.error("expected a newline, ',' or '}' after match arm")
        self.expect_op("}")
        return A.Match(subject, arms, start.line, start.col)

    # ------------------------------------------------------------------
    # patterns
    # ------------------------------------------------------------------
    def parse_pattern(self):
        pattern = self.parse_pattern_primary()
        if self.match_kw("as"):
            name = self.expect_ident("binding name")
            pattern = A.PAs(pattern, name, pattern.line, pattern.col)
        if self.check_op("|"):
            alts = [pattern]
            while self.match_op("|"):
                alt = self.parse_pattern_primary()
                if self.match_kw("as"):
                    name = self.expect_ident("binding name")
                    alt = A.PAs(alt, name, alt.line, alt.col)
                alts.append(alt)
            pattern = A.POr(alts, pattern.line, pattern.col)
        return pattern

    def parse_pattern_primary(self):
        tok = self.current
        if tok.type == "NUMBER":
            self.advance()
            return A.PLiteral(tok.value, tok.line, tok.col)
        if tok.type == "STRING":
            self.advance()
            if len(tok.value) != 1 or not tok.value[0][0]:
                self.error("interpolated strings are not valid patterns", tok)
            return A.PLiteral(tok.value[0][1], tok.line, tok.col)
        if tok.type == "OP" and tok.value == "-" and self.peek().type == "NUMBER":
            self.advance()
            num = self.advance()
            return A.PLiteral(-num.value, tok.line, tok.col)
        if tok.type == "KEYWORD" and tok.value in ("true", "false", "nil"):
            self.advance()
            value = {"true": True, "false": False, "nil": None}[tok.value]
            return A.PLiteral(value, tok.line, tok.col)
        if tok.type == "IDENT":
            self.advance()
            if tok.value == "_":
                return A.PWildcard(tok.line, tok.col)
            name = tok.value
            # Dotted class name, e.g. shapes.Circle(...)
            while self.check_op(".") and self.peek().type == "IDENT":
                self.advance()
                name += "." + self.advance().value
            if self.check_op("("):
                return self.parse_class_pattern(name, tok)
            return A.PVar(name, tok.line, tok.col)
        if tok.type == "OP" and tok.value == "[":
            return self.parse_list_pattern()
        if tok.type == "OP" and tok.value == "{":
            return self.parse_map_pattern()
        if tok.type == "OP" and tok.value == "(":
            self.advance()
            self.skip_newlines()
            inner = self.parse_pattern()
            self.skip_newlines()
            self.expect_op(")")
            return inner
        self.error("invalid pattern")

    def parse_class_pattern(self, name, start):
        self.expect_op("(")
        args = []
        kwargs = []
        self.skip_newlines()
        while not self.check_op(")"):
            if (
                self.current.type in ("IDENT", "KEYWORD")
                and self.peek().type == "OP"
                and self.peek().value == ":"
            ):
                key = self.advance().value
                self.advance()  # :
                kwargs.append((key, self.parse_pattern()))
            else:
                args.append(self.parse_pattern())
            self.skip_newlines()
            if self.check_op(","):
                self.advance()
                self.skip_newlines()
                continue
            break
        self.skip_newlines()
        self.expect_op(")")
        return A.PClass(name, args, kwargs, start.line, start.col)

    def parse_list_pattern(self):
        start = self.expect_op("[")
        items = []
        rest = None
        self.skip_newlines()
        while not self.check_op("]"):
            if self.check_op("..."):
                self.advance()
                if self.current.type == "IDENT":
                    name = self.advance().value
                else:
                    self.error("expected a name for the rest pattern")
                rest = name
                self.skip_newlines()
                break
            items.append(self.parse_pattern())
            self.skip_newlines()
            if self.check_op(","):
                self.advance()
                self.skip_newlines()
                continue
            break
        self.skip_newlines()
        self.expect_op("]")
        return A.PList(items, rest, start.line, start.col)

    def parse_map_pattern(self):
        start = self.expect_op("{")
        pairs = []
        rest = None
        self.skip_newlines()
        while not self.check_op("}"):
            if self.check_op("..."):
                self.advance()
                if self.current.type == "IDENT":
                    rest = self.advance().value
                else:
                    self.error("expected a name for the rest pattern")
                self.skip_newlines()
                break
            tok = self.current
            if tok.type in ("IDENT", "KEYWORD") and self.peek().type == "OP" and self.peek().value == ":":
                self.advance()
                key = tok.value
                self.advance()
                pattern = self.parse_pattern()
            elif tok.type in ("STRING", "NUMBER"):
                self.advance()
                key = tok.value[0][1] if tok.type == "STRING" else tok.value
                self.expect_op(":")
                pattern = self.parse_pattern()
            elif tok.type == "IDENT":
                self.advance()
                key = tok.value
                pattern = A.PVar(tok.value, tok.line, tok.col)
            else:
                self.error("invalid map pattern key")
            pairs.append((key, pattern))
            self.skip_newlines()
            if self.check_op(","):
                self.advance()
                self.skip_newlines()
                continue
            break
        self.skip_newlines()
        self.expect_op("}")
        return A.PMap(pairs, rest, start.line, start.col)

    # ------------------------------------------------------------------
    # strings
    # ------------------------------------------------------------------
    def build_string(self, tok):
        parts = []
        has_expr = False
        for is_literal, text in tok.value:
            if is_literal:
                parts.append(text)
            else:
                has_expr = True
                sub = Parser(tokenize(text, self.filename), self.filename, text)
                expr = sub.parse_expression_only()
                parts.append(expr)
        if not has_expr:
            return A.Literal("".join(parts), tok.line, tok.col)
        return A.Interp(parts, tok.line, tok.col)


def parse(source, filename="<input>"):
    tokens = tokenize(source, filename)
    parser = Parser(tokens, filename, source)
    return parser.parse_program()

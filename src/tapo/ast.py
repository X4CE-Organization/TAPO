"""Abstract syntax tree for TAPO.

All nodes are plain dataclasses.  Every node carries a source line/column so
that runtime errors and stack traces point at real code.  TAPO is
expression-oriented: blocks and control-flow constructs evaluate to a value,
and the top level of a file is simply a block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class Block:
    stmts: List[Any]
    line: int = 0
    col: int = 0


# ---------------------------------------------------------------------------
# expressions
# ---------------------------------------------------------------------------
@dataclass
class Literal:
    value: Any
    line: int = 0
    col: int = 0


@dataclass
class Interp:
    parts: List[Any]  # str for literal chunks, expressions otherwise
    line: int = 0
    col: int = 0


@dataclass
class ListLit:
    items: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class MapLit:
    pairs: List[Any]  # list of (key_expr, value_expr)
    line: int = 0
    col: int = 0


@dataclass
class Identifier:
    name: str
    line: int = 0
    col: int = 0


@dataclass
class Placeholder:
    line: int = 0
    col: int = 0


@dataclass
class SelfExpr:
    line: int = 0
    col: int = 0


@dataclass
class SuperExpr:
    method: Optional[str] = None
    line: int = 0
    col: int = 0


@dataclass
class Unary:
    op: str
    operand: Any
    line: int = 0
    col: int = 0


@dataclass
class Binary:
    op: str
    left: Any
    right: Any
    line: int = 0
    col: int = 0


@dataclass
class Pipe:
    left: Any
    right: Any
    has_placeholder: bool = False
    line: int = 0
    col: int = 0


@dataclass
class Assign:
    target: Any
    op: str
    value: Any
    line: int = 0
    col: int = 0


@dataclass
class Call:
    callee: Any
    args: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class Attr:
    obj: Any
    name: str
    safe: bool = False
    line: int = 0
    col: int = 0


@dataclass
class Index:
    obj: Any
    index: Any
    line: int = 0
    col: int = 0


@dataclass
class Splat:
    expr: Any
    line: int = 0
    col: int = 0


@dataclass
class Param:
    pattern: Any
    default: Any = None
    is_rest: bool = False
    line: int = 0
    col: int = 0


@dataclass
class Lambda:
    params: List[Param]
    body: Block
    name: str = "<lambda>"
    line: int = 0
    col: int = 0


@dataclass
class If:
    cond: Any
    then: Block
    otherwise: Optional[Block] = None
    line: int = 0
    col: int = 0


@dataclass
class While:
    cond: Any
    body: Block
    is_until: bool = False
    line: int = 0
    col: int = 0


@dataclass
class For:
    pattern: Any
    iterable: Any
    body: Block
    line: int = 0
    col: int = 0


@dataclass
class Loop:
    body: Block
    line: int = 0
    col: int = 0


@dataclass
class Return:
    value: Any = None
    line: int = 0
    col: int = 0


@dataclass
class Break:
    line: int = 0
    col: int = 0


@dataclass
class Continue:
    line: int = 0
    col: int = 0


@dataclass
class Yield:
    value: Any = None
    line: int = 0
    col: int = 0


@dataclass
class With:
    resource: Any
    name: Optional[str]
    body: Block
    line: int = 0
    col: int = 0


@dataclass
class Try:
    body: Block
    catch_name: Optional[str] = None
    catch_body: Optional[Block] = None
    finally_body: Optional[Block] = None
    line: int = 0
    col: int = 0


@dataclass
class Raise:
    value: Any
    line: int = 0
    col: int = 0


@dataclass
class MatchArm:
    pattern: Any
    guard: Any
    body: Block
    line: int = 0
    col: int = 0


@dataclass
class Match:
    subject: Any
    arms: List[MatchArm]
    line: int = 0
    col: int = 0


# ---------------------------------------------------------------------------
# declarations
# ---------------------------------------------------------------------------
@dataclass
class VarDecl:
    kind: str  # "let" or "var"
    pattern: Any
    value: Any = None
    line: int = 0
    col: int = 0


@dataclass
class FnDecl:
    name: str
    params: List[Param]
    body: Block
    static: bool = False
    line: int = 0
    col: int = 0


@dataclass
class GetterDecl:
    name: str
    body: Block
    line: int = 0
    col: int = 0


@dataclass
class SetterDecl:
    name: str
    param: Param
    body: Block
    line: int = 0
    col: int = 0


@dataclass
class UseAspect:
    expr: Any
    line: int = 0
    col: int = 0


@dataclass
class ClassDecl:
    name: str
    superclass: Any
    mixins: List[Any]
    members: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class EnumVariant:
    name: str
    fields: List[str]
    line: int = 0
    col: int = 0


@dataclass
class EnumDecl:
    name: str
    variants: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class MixinDecl:
    name: str
    members: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class Advice:
    kind: str  # before / after / around
    selector: str  # "*" or a method name
    params: List[Param]
    body: Block
    line: int = 0
    col: int = 0


@dataclass
class AspectDecl:
    name: str
    advices: List[Advice]
    line: int = 0
    col: int = 0


@dataclass
class Import:
    path: str
    alias: Optional[str] = None
    line: int = 0
    col: int = 0


@dataclass
class Export:
    decl: Any
    line: int = 0
    col: int = 0


# ---------------------------------------------------------------------------
# patterns
# ---------------------------------------------------------------------------
@dataclass
class PWildcard:
    line: int = 0
    col: int = 0


@dataclass
class PVar:
    name: str
    line: int = 0
    col: int = 0


@dataclass
class PLiteral:
    value: Any
    line: int = 0
    col: int = 0


@dataclass
class PList:
    items: List[Any]
    rest: Optional[str] = None
    line: int = 0
    col: int = 0


@dataclass
class PMap:
    pairs: List[Any]  # (key, pattern)
    rest: Optional[str] = None
    line: int = 0
    col: int = 0


@dataclass
class PClass:
    name: str
    args: List[Any] = field(default_factory=list)
    kwargs: List[Any] = field(default_factory=list)  # (field_name, pattern)
    line: int = 0
    col: int = 0


@dataclass
class POr:
    alts: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class PAs:
    pattern: Any
    name: str
    line: int = 0
    col: int = 0

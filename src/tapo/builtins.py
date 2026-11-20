"""Builtin classes, methods, global functions and standard modules for TAPO.

This module is intentionally dependency-free: only the Python standard library
is used.  The interpreter calls :func:`install` once at start-up to populate the
global environment.
"""

from __future__ import annotations

import functools
import json as _json
import math as _math
import os
import random as _random
import re as _re
import sys as _sys
import time as _time

from .objects import (
    TapoAspect,
    TapoBoundBuiltin,
    TapoBoundMethod,
    TapoBuiltin,
    TapoClass,
    TapoDynamicMethod,
    TapoFunction,
    TapoGenerator,
    TapoInstance,
    TapoMixin,
    TapoModule,
    TapoProceed,
    TapoRange,
)

VERSION = "0.0.1"
AUTHOR = "X4CE"
LICENSE = "MIT"

NOARG_PREDICATES = set()


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def fail(interp, cls, message):
    interp.error(cls, message, getattr(interp, "_builtin_node", None))


def arity(interp, args, name, minimum, maximum=None):
    if maximum is None:
        maximum = minimum
    if len(args) < minimum or len(args) > maximum:
        if minimum == maximum:
            expected = str(minimum)
        else:
            expected = "%d..%d" % (minimum, maximum)
        fail(interp, "ArgumentError", "%s expects %s argument(s), got %d" % (name, expected, len(args)))


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_num(value):
    return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)


def want_int(interp, value, name="value"):
    if not is_int(value):
        fail(interp, "TypeError", "%s must be an integer, got %s" % (name, interp.type_name(value)))
    return value


def want_num(interp, value, name="value"):
    if not is_num(value):
        fail(interp, "TypeError", "%s must be a number, got %s" % (name, interp.type_name(value)))
    return value


def want_str(interp, value, name="value"):
    if not isinstance(value, str):
        fail(interp, "TypeError", "%s must be a string, got %s" % (name, interp.type_name(value)))
    return value


def want_list(interp, value, name="value"):
    if not isinstance(value, list):
        fail(interp, "TypeError", "%s must be a list, got %s" % (name, interp.type_name(value)))
    return value


def want_map(interp, value, name="value"):
    if not isinstance(value, dict):
        fail(interp, "TypeError", "%s must be a map, got %s" % (name, interp.type_name(value)))
    return value


def to_list(interp, value):
    if isinstance(value, list):
        return list(value)
    return list(interp.iter_values(value))


def call(interp, fn, args):
    return interp.call_value(fn, list(args), getattr(interp, "_builtin_node", None))


def size_of(interp, value):
    if isinstance(value, (str, list, dict)):
        return len(value)
    if isinstance(value, TapoRange):
        return len(list(interp.iter_values(value)))
    if isinstance(value, TapoInstance):
        if interp.responds_to(value, "size"):
            return interp.invoke_method(value, "size", [])
        if interp.responds_to(value, "length"):
            return interp.invoke_method(value, "length", [])
    fail(interp, "TypeError", "%s does not have a size" % interp.type_name(value))


def truthy(value):
    return value is not None and value is not False


def each_item(interp, items, fn):
    for item in items:
        call(interp, fn, [item])


def compare_with(interp, comparator, left, right):
    result = call(interp, comparator, [left, right])
    if not is_num(result):
        fail(interp, "TypeError", "comparator must return a number")
    return result


# ---------------------------------------------------------------------------
# numeric methods
# ---------------------------------------------------------------------------
def int_abs(interp, recv, args):
    arity(interp, args, "abs", 0)
    return abs(recv)


def int_to_f(interp, recv, args):
    arity(interp, args, "to_f", 0)
    return float(recv)


def int_to_i(interp, recv, args):
    arity(interp, args, "to_i", 0)
    return recv


def int_to_s(interp, recv, args):
    arity(interp, args, "to_s", 0, 1)
    base = 10
    if args:
        base = want_int(interp, args[0], "base")
        if base < 2 or base > 36:
            fail(interp, "ValueError", "base must be between 2 and 36")
    if base == 10:
        return str(recv)
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    negative = recv < 0
    n = abs(recv)
    if n == 0:
        return "0"
    out = []
    while n:
        out.append(digits[n % base])
        n //= base
    if negative:
        out.append("-")
    return "".join(reversed(out))


def int_times(interp, recv, args):
    arity(interp, args, "times", 1)
    fn = args[0]
    for i in range(max(0, recv)):
        call(interp, fn, [i])
    return recv


def int_upto(interp, recv, args):
    arity(interp, args, "upto", 1, 2)
    end = want_int(interp, args[0], "end")
    fn = args[1] if len(args) > 1 else None
    values = range(recv, end + 1) if end >= recv else range(recv, end - 1, -1)
    if fn is None:
        return list(values)
    for i in values:
        call(interp, fn, [i])
    return recv


def int_downto(interp, recv, args):
    arity(interp, args, "downto", 1, 2)
    end = want_int(interp, args[0], "end")
    fn = args[1] if len(args) > 1 else None
    values = range(recv, end - 1, -1) if end <= recv else range(recv, end + 1)
    if fn is None:
        return list(values)
    for i in values:
        call(interp, fn, [i])
    return recv


def int_even(interp, recv, args):
    arity(interp, args, "even?", 0)
    return recv % 2 == 0


def int_odd(interp, recv, args):
    arity(interp, args, "odd?", 0)
    return recv % 2 != 0


def int_zero(interp, recv, args):
    arity(interp, args, "zero?", 0)
    return recv == 0


def int_positive(interp, recv, args):
    arity(interp, args, "positive?", 0)
    return recv > 0


def int_negative(interp, recv, args):
    arity(interp, args, "negative?", 0)
    return recv < 0


def int_clamp(interp, recv, args):
    arity(interp, args, "clamp", 2)
    low = want_num(interp, args[0], "low")
    high = want_num(interp, args[1], "high")
    if low > high:
        low, high = high, low
    return max(low, min(high, recv))


def int_digits(interp, recv, args):
    arity(interp, args, "digits", 0, 1)
    base = 10
    if args:
        base = want_int(interp, args[0], "base")
        if base < 2:
            fail(interp, "ValueError", "base must be at least 2")
    n = abs(recv)
    if n == 0:
        return [0]
    out = []
    while n:
        out.append(n % base)
        n //= base
    return out


def int_gcd(interp, recv, args):
    arity(interp, args, "gcd", 1)
    return _math.gcd(recv, want_int(interp, args[0], "other"))


def int_lcm(interp, recv, args):
    arity(interp, args, "lcm", 1)
    other = want_int(interp, args[0], "other")
    if recv == 0 or other == 0:
        return 0
    return abs(recv * other) // _math.gcd(recv, other)


def int_pow(interp, recv, args):
    arity(interp, args, "pow", 1)
    return interp.binary_op("**", recv, want_num(interp, args[0], "exponent"))


def int_floor(interp, recv, args):
    arity(interp, args, "floor", 0)
    return recv


def int_ceil(interp, recv, args):
    arity(interp, args, "ceil", 0)
    return recv


def int_round(interp, recv, args):
    arity(interp, args, "round", 0)
    return recv


def int_succ(interp, recv, args):
    arity(interp, args, "succ", 0)
    return recv + 1


def int_pred(interp, recv, args):
    arity(interp, args, "pred", 0)
    return recv - 1


def int_chr(interp, recv, args):
    arity(interp, args, "chr", 0)
    try:
        return chr(recv)
    except ValueError:
        fail(interp, "ValueError", "invalid character code %d" % recv)


def int_bit_length(interp, recv, args):
    arity(interp, args, "bit_length", 0)
    return abs(recv).bit_length()


def float_abs(interp, recv, args):
    arity(interp, args, "abs", 0)
    return abs(recv)


def float_floor(interp, recv, args):
    arity(interp, args, "floor", 0)
    return int(_math.floor(recv))


def float_ceil(interp, recv, args):
    arity(interp, args, "ceil", 0)
    return int(_math.ceil(recv))


def float_round(interp, recv, args):
    arity(interp, args, "round", 0, 1)
    if not args:
        return int(round(recv))
    digits = want_int(interp, args[0], "digits")
    return round(recv, digits)


def float_to_i(interp, recv, args):
    arity(interp, args, "to_i", 0)
    return int(recv)


def float_to_f(interp, recv, args):
    arity(interp, args, "to_f", 0)
    return recv


def float_truncate(interp, recv, args):
    arity(interp, args, "truncate", 0)
    return int(recv)


def float_nan(interp, recv, args):
    arity(interp, args, "nan?", 0)
    return _math.isnan(recv)


def float_infinite(interp, recv, args):
    arity(interp, args, "infinite?", 0)
    if _math.isinf(recv):
        return 1 if recv > 0 else -1
    return None


def float_finite(interp, recv, args):
    arity(interp, args, "finite?", 0)
    return _math.isfinite(recv)


def float_sqrt(interp, recv, args):
    arity(interp, args, "sqrt", 0)
    if recv < 0:
        fail(interp, "ValueError", "cannot take the square root of a negative number")
    return _math.sqrt(recv)


# ---------------------------------------------------------------------------
# string methods
# ---------------------------------------------------------------------------
def str_size(interp, recv, args):
    arity(interp, args, "size", 0)
    return len(recv)


def str_length(interp, recv, args):
    arity(interp, args, "length", 0)
    return len(recv)


def str_empty(interp, recv, args):
    arity(interp, args, "empty?", 0)
    return len(recv) == 0


def str_blank(interp, recv, args):
    arity(interp, args, "blank?", 0)
    return recv.strip() == ""


def str_upper(interp, recv, args):
    arity(interp, args, "upper", 0)
    return recv.upper()


def str_lower(interp, recv, args):
    arity(interp, args, "lower", 0)
    return recv.lower()


def str_capitalize(interp, recv, args):
    arity(interp, args, "capitalize", 0)
    return recv[:1].upper() + recv[1:].lower()


def str_title(interp, recv, args):
    arity(interp, args, "title", 0)
    return recv.title()


def str_swapcase(interp, recv, args):
    arity(interp, args, "swapcase", 0)
    return recv.swapcase()


def str_strip(interp, recv, args):
    arity(interp, args, "strip", 0, 1)
    if args:
        return recv.strip(want_str(interp, args[0], "characters"))
    return recv.strip()


def str_lstrip(interp, recv, args):
    arity(interp, args, "lstrip", 0, 1)
    if args:
        return recv.lstrip(want_str(interp, args[0], "characters"))
    return recv.lstrip()


def str_rstrip(interp, recv, args):
    arity(interp, args, "rstrip", 0, 1)
    if args:
        return recv.rstrip(want_str(interp, args[0], "characters"))
    return recv.rstrip()


def str_split(interp, recv, args):
    arity(interp, args, "split", 0, 2)
    if not args or args[0] is None:
        return recv.split()
    sep = want_str(interp, args[0], "separator")
    if len(args) > 1:
        limit = want_int(interp, args[1], "limit")
        return recv.split(sep, limit)
    return recv.split(sep)


def str_chars(interp, recv, args):
    arity(interp, args, "chars", 0)
    return list(recv)


def str_bytes(interp, recv, args):
    arity(interp, args, "bytes", 0)
    return list(recv.encode("utf-8"))


def str_lines(interp, recv, args):
    arity(interp, args, "lines", 0)
    return recv.splitlines()


def str_replace(interp, recv, args):
    arity(interp, args, "replace", 2)
    return recv.replace(want_str(interp, args[0], "old"), want_str(interp, args[1], "new"))


def str_contains(interp, recv, args):
    arity(interp, args, "contains", 1)
    return want_str(interp, args[0], "substring") in recv


def str_starts_with(interp, recv, args):
    arity(interp, args, "starts_with", 1)
    return recv.startswith(want_str(interp, args[0], "prefix"))


def str_ends_with(interp, recv, args):
    arity(interp, args, "ends_with", 1)
    return recv.endswith(want_str(interp, args[0], "suffix"))


def str_index_of(interp, recv, args):
    arity(interp, args, "index_of", 1, 2)
    needle = want_str(interp, args[0], "substring")
    start = 0
    if len(args) > 1:
        start = want_int(interp, args[1], "start")
    found = recv.find(needle, start)
    return found if found >= 0 else None


def str_slice(interp, recv, args):
    arity(interp, args, "slice", 1, 2)
    if isinstance(args[0], TapoRange):
        return recv[interp.slice_from_range(args[0])]
    start = want_int(interp, args[0], "start")
    if len(args) == 1:
        return recv[start]
    length = want_int(interp, args[1], "length")
    return recv[start : start + length]


def str_reverse(interp, recv, args):
    arity(interp, args, "reverse", 0)
    return recv[::-1]


def str_repeat(interp, recv, args):
    arity(interp, args, "repeat", 1)
    count = want_int(interp, args[0], "count")
    if count < 0:
        fail(interp, "ValueError", "count cannot be negative")
    return recv * count


def str_each_char(interp, recv, args):
    arity(interp, args, "each_char", 1)
    for ch in recv:
        call(interp, args[0], [ch])
    return recv


def str_to_i(interp, recv, args):
    arity(interp, args, "to_i", 0, 1)
    base = 10
    if args:
        base = want_int(interp, args[0], "base")
    text = recv.strip()
    try:
        return int(text, base)
    except ValueError:
        # Ruby-style lenient conversion: parse the longest numeric prefix.
        match = _re.match(r"^[+-]?[0-9]+", text)
        if not match:
            return 0
        return int(match.group(0), base)


def str_to_f(interp, recv, args):
    arity(interp, args, "to_f", 0)
    text = recv.strip()
    try:
        return float(text)
    except ValueError:
        match = _re.match(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text)
        if not match:
            return 0.0
        return float(match.group(0))


def str_count(interp, recv, args):
    arity(interp, args, "count", 1)
    return recv.count(want_str(interp, args[0], "substring"))


def str_center(interp, recv, args):
    arity(interp, args, "center", 1, 2)
    width = want_int(interp, args[0], "width")
    pad = " " if len(args) == 1 else want_str(interp, args[1], "padding")
    if len(pad) != 1:
        fail(interp, "ValueError", "center padding must be exactly one character")
    return recv.center(width, pad)


def str_ljust(interp, recv, args):
    arity(interp, args, "ljust", 1, 2)
    width = want_int(interp, args[0], "width")
    pad = " " if len(args) == 1 else want_str(interp, args[1], "padding")
    if len(pad) != 1:
        fail(interp, "ValueError", "ljust padding must be exactly one character")
    return recv.ljust(width, pad)


def str_rjust(interp, recv, args):
    arity(interp, args, "rjust", 1, 2)
    width = want_int(interp, args[0], "width")
    pad = " " if len(args) == 1 else want_str(interp, args[1], "padding")
    if len(pad) != 1:
        fail(interp, "ValueError", "rjust padding must be exactly one character")
    return recv.rjust(width, pad)


def str_zfill(interp, recv, args):
    arity(interp, args, "zfill", 1)
    return recv.zfill(want_int(interp, args[0], "width"))


def str_join(interp, recv, args):
    arity(interp, args, "join", 1)
    items = to_list(interp, args[0])
    for item in items:
        if not isinstance(item, str):
            fail(interp, "TypeError", "join expects a list of strings, got %s" % interp.type_name(item))
    return recv.join(items)


def str_ord(interp, recv, args):
    arity(interp, args, "ord", 0)
    if len(recv) != 1:
        fail(interp, "ValueError", "ord expects a single-character string")
    return ord(recv)


def str_codepoints(interp, recv, args):
    arity(interp, args, "codepoints", 0)
    return [ord(ch) for ch in recv]


# ---------------------------------------------------------------------------
# list methods
# ---------------------------------------------------------------------------
def list_size(interp, recv, args):
    arity(interp, args, "size", 0)
    return len(recv)


def list_length(interp, recv, args):
    arity(interp, args, "length", 0)
    return len(recv)


def list_empty(interp, recv, args):
    arity(interp, args, "empty?", 0)
    return len(recv) == 0


def list_push(interp, recv, args):
    arity(interp, args, "push", 1)
    recv.append(args[0])
    return recv


def list_pop(interp, recv, args):
    arity(interp, args, "pop", 0)
    if not recv:
        return None
    return recv.pop()


def list_shift(interp, recv, args):
    arity(interp, args, "shift", 0)
    if not recv:
        return None
    return recv.pop(0)


def list_unshift(interp, recv, args):
    arity(interp, args, "unshift", 1)
    recv.insert(0, args[0])
    return recv


def list_insert(interp, recv, args):
    arity(interp, args, "insert", 2)
    index = want_int(interp, args[0], "index")
    if index < 0:
        index = max(0, len(recv) + index)
    recv.insert(index, args[1])
    return recv


def list_remove(interp, recv, args):
    arity(interp, args, "remove", 1)
    target = args[0]
    for i, item in enumerate(recv):
        if interp.tapo_equals(item, target):
            recv.pop(i)
            return target
    return None


def list_delete_at(interp, recv, args):
    arity(interp, args, "delete_at", 1)
    index = want_int(interp, args[0], "index")
    try:
        return recv.pop(index)
    except IndexError:
        return None


def list_clear(interp, recv, args):
    arity(interp, args, "clear", 0)
    recv.clear()
    return recv


def list_compact(interp, recv, args):
    arity(interp, args, "compact", 0)
    return [item for item in recv if item is not None]


def list_first(interp, recv, args):
    arity(interp, args, "first", 0, 1)
    if not args:
        return recv[0] if recv else None
    count = want_int(interp, args[0], "count")
    return recv[: max(0, count)]


def list_last(interp, recv, args):
    arity(interp, args, "last", 0, 1)
    if not args:
        return recv[-1] if recv else None
    count = want_int(interp, args[0], "count")
    if count <= 0:
        return []
    return recv[-count:]


def list_take(interp, recv, args):
    arity(interp, args, "take", 1)
    count = want_int(interp, args[0], "count")
    return recv[: max(0, count)]


def list_drop(interp, recv, args):
    arity(interp, args, "drop", 1)
    count = want_int(interp, args[0], "count")
    return recv[max(0, count) :]


def list_each(interp, recv, args):
    arity(interp, args, "each", 1)
    each_item(interp, recv, args[0])
    return recv


def list_each_with_index(interp, recv, args):
    arity(interp, args, "each_with_index", 1)
    for index, item in enumerate(recv):
        call(interp, args[0], [item, index])
    return recv


def list_map(interp, recv, args):
    arity(interp, args, "map", 1)
    return [call(interp, args[0], [item]) for item in recv]


def list_flat_map(interp, recv, args):
    arity(interp, args, "flat_map", 1)
    out = []
    for item in recv:
        value = call(interp, args[0], [item])
        if isinstance(value, list):
            out.extend(value)
        else:
            out.append(value)
    return out


def list_filter(interp, recv, args):
    arity(interp, args, "filter", 1)
    return [item for item in recv if truthy(call(interp, args[0], [item]))]


def list_reject(interp, recv, args):
    arity(interp, args, "reject", 1)
    return [item for item in recv if not truthy(call(interp, args[0], [item]))]


def list_find(interp, recv, args):
    arity(interp, args, "find", 1)
    for item in recv:
        if truthy(call(interp, args[0], [item])):
            return item
    return None


def list_find_index(interp, recv, args):
    arity(interp, args, "find_index", 1)
    for index, item in enumerate(recv):
        if truthy(call(interp, args[0], [item])):
            return index
    return None


def list_any(interp, recv, args):
    arity(interp, args, "any?", 0, 1)
    if args:
        return any(truthy(call(interp, args[0], [item])) for item in recv)
    return any(truthy(item) for item in recv)


def list_all(interp, recv, args):
    arity(interp, args, "all?", 0, 1)
    if args:
        return all(truthy(call(interp, args[0], [item])) for item in recv)
    return all(truthy(item) for item in recv)


def list_none(interp, recv, args):
    arity(interp, args, "none?", 0, 1)
    if args:
        return not any(truthy(call(interp, args[0], [item])) for item in recv)
    return not any(truthy(item) for item in recv)


def list_count(interp, recv, args):
    arity(interp, args, "count", 0, 1)
    if not args:
        return len(recv)
    if isinstance(args[0], (TapoFunction, TapoBoundMethod, TapoBuiltin, TapoBoundBuiltin)):
        return sum(1 for item in recv if truthy(call(interp, args[0], [item])))
    return sum(1 for item in recv if interp.tapo_equals(item, args[0]))


def list_reduce(interp, recv, args):
    arity(interp, args, "reduce", 1, 2)
    if len(args) == 1:
        fn = args[0]
        if not recv:
            return None
        acc = recv[0]
        items = recv[1:]
    else:
        acc = args[0]
        fn = args[1]
        items = recv
    for item in items:
        acc = call(interp, fn, [acc, item])
    return acc


def list_sum(interp, recv, args):
    arity(interp, args, "sum", 0, 1)
    acc = 0 if not args else args[0]
    for item in recv:
        acc = interp.binary_op("+", acc, item)
    return acc


def list_min(interp, recv, args):
    arity(interp, args, "min", 0)
    if not recv:
        return None
    best = recv[0]
    for item in recv[1:]:
        if interp.compare_values(item, best) < 0:
            best = item
    return best


def list_max(interp, recv, args):
    arity(interp, args, "max", 0)
    if not recv:
        return None
    best = recv[0]
    for item in recv[1:]:
        if interp.compare_values(item, best) > 0:
            best = item
    return best


def list_min_by(interp, recv, args):
    arity(interp, args, "min_by", 1)
    if not recv:
        return None
    best = recv[0]
    best_key = call(interp, args[0], [best])
    for item in recv[1:]:
        key = call(interp, args[0], [item])
        if interp.compare_values(key, best_key) < 0:
            best, best_key = item, key
    return best


def list_max_by(interp, recv, args):
    arity(interp, args, "max_by", 1)
    if not recv:
        return None
    best = recv[0]
    best_key = call(interp, args[0], [best])
    for item in recv[1:]:
        key = call(interp, args[0], [item])
        if interp.compare_values(key, best_key) > 0:
            best, best_key = item, key
    return best


def list_sort(interp, recv, args):
    arity(interp, args, "sort", 0, 1)
    if not args:
        return sorted(recv, key=functools.cmp_to_key(lambda a, b: interp.compare_values(a, b)))
    return sorted(recv, key=functools.cmp_to_key(lambda a, b: compare_with(interp, args[0], a, b)))


def list_sort_by(interp, recv, args):
    arity(interp, args, "sort_by", 1)
    return sorted(recv, key=functools.cmp_to_key(lambda a, b: interp.compare_values(call(interp, args[0], [a]), call(interp, args[0], [b]))))


def list_reverse(interp, recv, args):
    arity(interp, args, "reverse", 0)
    return list(reversed(recv))


def list_join(interp, recv, args):
    arity(interp, args, "join", 0, 1)
    sep = "" if not args else want_str(interp, args[0], "separator")
    parts = []
    for item in recv:
        if isinstance(item, str):
            parts.append(item)
        else:
            parts.append(interp.to_s(item))
    return sep.join(parts)


def list_contains(interp, recv, args):
    arity(interp, args, "contains", 1)
    return any(interp.tapo_equals(item, args[0]) for item in recv)


def list_index_of(interp, recv, args):
    arity(interp, args, "index_of", 1)
    for index, item in enumerate(recv):
        if interp.tapo_equals(item, args[0]):
            return index
    return None


def list_flatten(interp, recv, args):
    arity(interp, args, "flatten", 0, 1)
    depth = None
    if args:
        depth = want_int(interp, args[0], "depth")

    def flatten(items, level):
        out = []
        for item in items:
            if isinstance(item, list) and (level is None or level > 0):
                out.extend(flatten(item, None if level is None else level - 1))
            else:
                out.append(item)
        return out

    return flatten(recv, depth)


def list_uniq(interp, recv, args):
    arity(interp, args, "uniq", 0)
    out = []
    for item in recv:
        if not any(interp.tapo_equals(item, other) for other in out):
            out.append(item)
    return out


def list_zip(interp, recv, args):
    arity(interp, args, "zip", 1)
    other = to_list(interp, args[0])
    return [[item, other[index] if index < len(other) else None] for index, item in enumerate(recv)]


def list_enumerate(interp, recv, args):
    arity(interp, args, "enumerate", 0, 1)
    start = 0 if not args else want_int(interp, args[0], "start")
    return [[start + index, item] for index, item in enumerate(recv)]


def list_group_by(interp, recv, args):
    arity(interp, args, "group_by", 1)
    out = {}
    for item in recv:
        key = call(interp, args[0], [item])
        out.setdefault(key, []).append(item)
    return out


def list_partition(interp, recv, args):
    arity(interp, args, "partition", 1)
    yes = []
    no = []
    for item in recv:
        (yes if truthy(call(interp, args[0], [item])) else no).append(item)
    return [yes, no]


def list_each_slice(interp, recv, args):
    arity(interp, args, "each_slice", 1, 2)
    size = want_int(interp, args[0], "size")
    if size <= 0:
        fail(interp, "ValueError", "slice size must be positive")
    chunks = [recv[index : index + size] for index in range(0, len(recv), size)]
    if len(args) == 1:
        return chunks
    for chunk in chunks:
        call(interp, args[1], [chunk])
    return recv


def list_rotate(interp, recv, args):
    arity(interp, args, "rotate", 0, 1)
    if not recv:
        return []
    amount = 1 if not args else want_int(interp, args[0], "amount")
    amount %= len(recv)
    return recv[amount:] + recv[:amount]


def list_shuffle(interp, recv, args):
    arity(interp, args, "shuffle", 0)
    out = list(recv)
    _random.shuffle(out)
    return out


def list_sample(interp, recv, args):
    arity(interp, args, "sample", 0, 1)
    if not recv:
        return None
    if not args:
        return _random.choice(recv)
    count = want_int(interp, args[0], "count")
    if count > len(recv):
        fail(interp, "ValueError", "sample size is larger than the list")
    return _random.sample(recv, count)


def list_to_map(interp, recv, args):
    arity(interp, args, "to_map", 0)
    out = {}
    for item in recv:
        if not isinstance(item, list) or len(item) != 2:
            fail(interp, "TypeError", "to_map expects a list of [key, value] pairs")
        out[item[0]] = item[1]
    return out


def list_slice(interp, recv, args):
    arity(interp, args, "slice", 1, 2)
    if isinstance(args[0], TapoRange):
        return recv[interp.slice_from_range(args[0])]
    start = want_int(interp, args[0], "start")
    if len(args) == 1:
        return recv[start]
    return recv[start : start + want_int(interp, args[1], "length")]


# ---------------------------------------------------------------------------
# map methods
# ---------------------------------------------------------------------------
def map_size(interp, recv, args):
    arity(interp, args, "size", 0)
    return len(recv)


def map_empty(interp, recv, args):
    arity(interp, args, "empty?", 0)
    return len(recv) == 0


def map_keys(interp, recv, args):
    arity(interp, args, "keys", 0)
    return list(recv.keys())


def map_values(interp, recv, args):
    arity(interp, args, "values", 0)
    return list(recv.values())


def map_pairs(interp, recv, args):
    arity(interp, args, "pairs", 0)
    return [[key, value] for key, value in recv.items()]


def map_to_list(interp, recv, args):
    arity(interp, args, "to_list", 0)
    return [[key, value] for key, value in recv.items()]


def map_get(interp, recv, args):
    arity(interp, args, "get", 1, 2)
    if args[0] in recv:
        return recv[args[0]]
    if len(args) > 1:
        return args[1]
    return None


def map_fetch(interp, recv, args):
    arity(interp, args, "fetch", 1)
    if args[0] not in recv:
        fail(interp, "KeyError", "key %s not found" % interp.inspect(args[0]))
    return recv[args[0]]


def map_set(interp, recv, args):
    arity(interp, args, "set", 2)
    recv[args[0]] = args[1]
    return recv


def map_has_key(interp, recv, args):
    arity(interp, args, "has_key?", 1)
    return args[0] in recv


def map_has_value(interp, recv, args):
    arity(interp, args, "has_value?", 1)
    return any(interp.tapo_equals(value, args[0]) for value in recv.values())


def map_delete(interp, recv, args):
    arity(interp, args, "delete", 1)
    if args[0] in recv:
        return recv.pop(args[0])
    return None


def map_merge(interp, recv, args):
    arity(interp, args, "merge", 1)
    other = want_map(interp, args[0], "other")
    out = dict(recv)
    out.update(other)
    return out


def map_merge_bang(interp, recv, args):
    arity(interp, args, "merge!", 1)
    other = want_map(interp, args[0], "other")
    recv.update(other)
    return recv


def map_each(interp, recv, args):
    arity(interp, args, "each", 1)
    for key, value in recv.items():
        call(interp, args[0], [[key, value]])
    return recv


def map_each_key(interp, recv, args):
    arity(interp, args, "each_key", 1)
    for key in recv:
        call(interp, args[0], [key])
    return recv


def map_each_value(interp, recv, args):
    arity(interp, args, "each_value", 1)
    for value in recv.values():
        call(interp, args[0], [value])
    return recv


def map_map(interp, recv, args):
    arity(interp, args, "map", 1)
    return [call(interp, args[0], [key, value]) for key, value in recv.items()]


def map_map_values(interp, recv, args):
    arity(interp, args, "map_values", 1)
    return {key: call(interp, args[0], [key, value]) for key, value in recv.items()}


def map_filter(interp, recv, args):
    arity(interp, args, "filter", 1)
    return {key: value for key, value in recv.items() if truthy(call(interp, args[0], [key, value]))}


def map_reject(interp, recv, args):
    arity(interp, args, "reject", 1)
    return {key: value for key, value in recv.items() if not truthy(call(interp, args[0], [key, value]))}


def map_invert(interp, recv, args):
    arity(interp, args, "invert", 0)
    try:
        return {value: key for key, value in recv.items()}
    except TypeError:
        fail(interp, "TypeError", "cannot invert a map with unhashable values")


def map_any(interp, recv, args):
    arity(interp, args, "any?", 0, 1)
    if args:
        return any(truthy(call(interp, args[0], [key, value])) for key, value in recv.items())
    return any(truthy(value) for value in recv.values())


def map_all(interp, recv, args):
    arity(interp, args, "all?", 0, 1)
    if args:
        return all(truthy(call(interp, args[0], [key, value])) for key, value in recv.items())
    return all(truthy(value) for value in recv.values())


def map_none(interp, recv, args):
    arity(interp, args, "none?", 0, 1)
    if args:
        return not any(truthy(call(interp, args[0], [key, value])) for key, value in recv.items())
    return not any(truthy(value) for value in recv.values())


# ---------------------------------------------------------------------------
# range methods
# ---------------------------------------------------------------------------
def range_each(interp, recv, args):
    arity(interp, args, "each", 1)
    each_item(interp, interp.iter_values(recv), args[0])
    return recv


def range_to_list(interp, recv, args):
    arity(interp, args, "to_list", 0)
    return list(interp.iter_values(recv))


def range_map(interp, recv, args):
    arity(interp, args, "map", 1)
    return [call(interp, args[0], [item]) for item in interp.iter_values(recv)]


def range_filter(interp, recv, args):
    arity(interp, args, "filter", 1)
    return [item for item in interp.iter_values(recv) if truthy(call(interp, args[0], [item]))]


def range_size(interp, recv, args):
    arity(interp, args, "size", 0)
    return len(list(interp.iter_values(recv)))


def range_empty(interp, recv, args):
    arity(interp, args, "empty?", 0)
    return len(list(interp.iter_values(recv))) == 0


def range_contains(interp, recv, args):
    arity(interp, args, "contains", 1)
    return interp.contains(recv, args[0])


def range_first(interp, recv, args):
    arity(interp, args, "first", 0)
    values = list(interp.iter_values(recv))
    return values[0] if values else None


def range_last(interp, recv, args):
    arity(interp, args, "last", 0)
    values = list(interp.iter_values(recv))
    return values[-1] if values else None


def range_min(interp, recv, args):
    arity(interp, args, "min", 0)
    values = list(interp.iter_values(recv))
    return min(values) if values else None


def range_max(interp, recv, args):
    arity(interp, args, "max", 0)
    values = list(interp.iter_values(recv))
    return max(values) if values else None


def range_sum(interp, recv, args):
    arity(interp, args, "sum", 0, 1)
    acc = 0 if not args else args[0]
    for item in interp.iter_values(recv):
        acc = interp.binary_op("+", acc, item)
    return acc


def range_reduce(interp, recv, args):
    arity(interp, args, "reduce", 1, 2)
    values = list(interp.iter_values(recv))
    if len(args) == 1:
        if not values:
            return None
        acc = values[0]
        fn = args[0]
        for item in values[1:]:
            acc = call(interp, fn, [acc, item])
        return acc
    acc = args[0]
    fn = args[1]
    for item in values:
        acc = call(interp, fn, [acc, item])
    return acc


def range_reverse(interp, recv, args):
    arity(interp, args, "reverse", 0)
    return list(reversed(list(interp.iter_values(recv))))


def range_step(interp, recv, args):
    arity(interp, args, "step", 1, 2)
    step = want_num(interp, args[0], "step")
    if step == 0:
        fail(interp, "ValueError", "step cannot be zero")
    values = []
    current = recv.start
    direction = 1 if recv.end >= recv.start else -1
    if step < 0:
        direction = -direction
    condition = (lambda x: x <= recv.end) if direction > 0 else (lambda x: x >= recv.end)
    while condition(current):
        if not recv.inclusive and current == recv.end:
            break
        values.append(current)
        current += abs(step) * direction
    if len(args) > 1:
        for item in values:
            call(interp, args[1], [item])
        return recv
    return values


# ---------------------------------------------------------------------------
# function methods
# ---------------------------------------------------------------------------
def function_call(interp, recv, args):
    return interp.call_value(recv, list(args), getattr(interp, "_builtin_node", None))


def function_arity(interp, recv, args):
    arity(interp, args, "arity", 0)
    if isinstance(recv, TapoFunction):
        return len([p for p in recv.params if not p.is_rest and p.default is None])
    return 0


def function_parameters(interp, recv, args):
    arity(interp, args, "parameters", 0)
    if not isinstance(recv, TapoFunction):
        return []
    out = []
    for param in recv.params:
        if isinstance(param.pattern, object) and hasattr(param.pattern, "name"):
            out.append(param.pattern.name)
        else:
            out.append("_")
    return out


def function_name(interp, recv, args):
    arity(interp, args, "name", 0)
    return getattr(recv, "name", "<fn>")


def bool_to_i(interp, recv, args):
    arity(interp, args, "to_i", 0)
    return 1 if recv else 0


# ---------------------------------------------------------------------------
# method tables
# ---------------------------------------------------------------------------
INT_METHODS = {
    "abs": int_abs,
    "to_f": int_to_f,
    "to_i": int_to_i,
    "to_s": int_to_s,
    "times": int_times,
    "upto": int_upto,
    "downto": int_downto,
    "even?": int_even,
    "odd?": int_odd,
    "zero?": int_zero,
    "positive?": int_positive,
    "negative?": int_negative,
    "clamp": int_clamp,
    "digits": int_digits,
    "gcd": int_gcd,
    "lcm": int_lcm,
    "pow": int_pow,
    "floor": int_floor,
    "ceil": int_ceil,
    "round": int_round,
    "succ": int_succ,
    "pred": int_pred,
    "chr": int_chr,
    "bit_length": int_bit_length,
}

FLOAT_METHODS = {
    "abs": float_abs,
    "floor": float_floor,
    "ceil": float_ceil,
    "round": float_round,
    "to_i": float_to_i,
    "to_f": float_to_f,
    "truncate": float_truncate,
    "nan?": float_nan,
    "infinite?": float_infinite,
    "finite?": float_finite,
    "sqrt": float_sqrt,
}

STRING_METHODS = {
    "size": str_size,
    "length": str_length,
    "empty?": str_empty,
    "blank?": str_blank,
    "upper": str_upper,
    "lower": str_lower,
    "upcase": str_upper,
    "downcase": str_lower,
    "capitalize": str_capitalize,
    "title": str_title,
    "swapcase": str_swapcase,
    "strip": str_strip,
    "trim": str_strip,
    "lstrip": str_lstrip,
    "rstrip": str_rstrip,
    "split": str_split,
    "chars": str_chars,
    "bytes": str_bytes,
    "lines": str_lines,
    "replace": str_replace,
    "contains": str_contains,
    "starts_with": str_starts_with,
    "ends_with": str_ends_with,
    "index_of": str_index_of,
    "slice": str_slice,
    "substring": str_slice,
    "reverse": str_reverse,
    "repeat": str_repeat,
    "each_char": str_each_char,
    "to_i": str_to_i,
    "to_f": str_to_f,
    "count": str_count,
    "center": str_center,
    "ljust": str_ljust,
    "rjust": str_rjust,
    "zfill": str_zfill,
    "join": str_join,
    "ord": str_ord,
    "codepoints": str_codepoints,
}

LIST_METHODS = {
    "size": list_size,
    "length": list_length,
    "empty?": list_empty,
    "push": list_push,
    "append": list_push,
    "pop": list_pop,
    "shift": list_shift,
    "unshift": list_unshift,
    "insert": list_insert,
    "remove": list_remove,
    "delete": list_remove,
    "delete_at": list_delete_at,
    "clear": list_clear,
    "compact": list_compact,
    "first": list_first,
    "last": list_last,
    "take": list_take,
    "drop": list_drop,
    "each": list_each,
    "each_with_index": list_each_with_index,
    "map": list_map,
    "collect": list_map,
    "flat_map": list_flat_map,
    "filter": list_filter,
    "select": list_filter,
    "reject": list_reject,
    "find": list_find,
    "find_index": list_find_index,
    "any?": list_any,
    "all?": list_all,
    "none?": list_none,
    "count": list_count,
    "reduce": list_reduce,
    "sum": list_sum,
    "min": list_min,
    "max": list_max,
    "min_by": list_min_by,
    "max_by": list_max_by,
    "sort": list_sort,
    "sort_by": list_sort_by,
    "reverse": list_reverse,
    "join": list_join,
    "contains": list_contains,
    "index_of": list_index_of,
    "flatten": list_flatten,
    "uniq": list_uniq,
    "unique": list_uniq,
    "zip": list_zip,
    "enumerate": list_enumerate,
    "group_by": list_group_by,
    "partition": list_partition,
    "each_slice": list_each_slice,
    "rotate": list_rotate,
    "shuffle": list_shuffle,
    "sample": list_sample,
    "to_map": list_to_map,
    "slice": list_slice,
}

MAP_METHODS = {
    "size": map_size,
    "length": map_size,
    "empty?": map_empty,
    "keys": map_keys,
    "values": map_values,
    "pairs": map_pairs,
    "to_list": map_to_list,
    "get": map_get,
    "fetch": map_fetch,
    "set": map_set,
    "has_key?": map_has_key,
    "key?": map_has_key,
    "has_value?": map_has_value,
    "value?": map_has_value,
    "delete": map_delete,
    "merge": map_merge,
    "merge!": map_merge_bang,
    "update": map_merge_bang,
    "each": map_each,
    "each_key": map_each_key,
    "each_value": map_each_value,
    "map": map_map,
    "map_values": map_map_values,
    "filter": map_filter,
    "select": map_filter,
    "reject": map_reject,
    "invert": map_invert,
    "any?": map_any,
    "all?": map_all,
    "none?": map_none,
}

RANGE_METHODS = {
    "each": range_each,
    "to_list": range_to_list,
    "map": range_map,
    "filter": range_filter,
    "size": range_size,
    "length": range_size,
    "empty?": range_empty,
    "contains": range_contains,
    "first": range_first,
    "last": range_last,
    "min": range_min,
    "max": range_max,
    "sum": range_sum,
    "reduce": range_reduce,
    "reverse": range_reverse,
    "step": range_step,
}

FUNCTION_METHODS = {
    "call": function_call,
    "arity": function_arity,
    "parameters": function_parameters,
    "name": function_name,
}

BOOL_METHODS = {
    "to_i": bool_to_i,
}

def generator_next(interp, gen, args):
    arity(interp, args, "Generator.next", 0)
    return gen.next_value(getattr(interp, "_builtin_node", None))

def generator_done(interp, gen, args):
    arity(interp, args, "Generator.done?", 0)
    return bool(gen.done)

def generator_each(interp, gen, args):
    arity(interp, args, "Generator.each", 1)
    callback = args[0]
    for value in gen:
        interp.call_value(callback, [value], getattr(interp, "_builtin_node", None))
    return None

def generator_to_list(interp, gen, args):
    arity(interp, args, "Generator.to_list", 0)
    return list(gen)

def generator_take(interp, gen, args):
    arity(interp, args, "Generator.take", 1)
    count = want_int(interp, args[0], "count")
    if count < 0:
        fail(interp, "ArgumentError", "count must be non-negative")
    out = []
    while len(out) < count:
        try:
            out.append(next(gen))
        except StopIteration:
            break
    return out

def generator_close(interp, gen, args):
    arity(interp, args, "Generator.close", 0)
    gen.close()
    return None

GENERATOR_METHODS = {
    "next": generator_next,
    "done?": generator_done,
    "each": generator_each,
    "to_list": generator_to_list,
    "take": generator_take,
    "close": generator_close,
}

NIL_METHODS = {}

NOARG_PREDICATES.update(
    {
        "size",
        "length",
        "empty?",
        "blank?",
        "zero?",
        "positive?",
        "negative?",
        "even?",
        "odd?",
        "nan?",
        "finite?",
        "infinite?",
        "any?",
        "all?",
        "none?",
        "done?",
    }
)


def table_for(value):
    if value is None:
        return NIL_METHODS
    if isinstance(value, bool):
        return BOOL_METHODS
    if is_int(value):
        return INT_METHODS
    if isinstance(value, float):
        return FLOAT_METHODS
    if isinstance(value, str):
        return STRING_METHODS
    if isinstance(value, list):
        return LIST_METHODS
    if isinstance(value, dict):
        return MAP_METHODS
    if isinstance(value, TapoRange):
        return RANGE_METHODS
    if isinstance(value, TapoGenerator):
        return GENERATOR_METHODS
    if isinstance(
        value,
        (TapoFunction, TapoBoundMethod, TapoBuiltin, TapoBoundBuiltin, TapoDynamicMethod, TapoProceed),
    ):
        return FUNCTION_METHODS
    return None


def lookup_method(value, name):
    table = table_for(value)
    if table is None:
        return None
    return table.get(name)


def method_names(value):
    table = table_for(value)
    if table is None:
        return []
    return sorted(table.keys())


# ---------------------------------------------------------------------------
# constructors for builtin classes
# ---------------------------------------------------------------------------
def ctor_int(interp, args, node):
    arity(interp, args, "Int", 0, 2)
    if not args:
        return 0
    value = args[0]
    if isinstance(value, bool):
        return 1 if value else 0
    if is_int(value):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        base = 10
        if len(args) > 1:
            base = want_int(interp, args[1], "base")
        try:
            return int(value.strip(), base)
        except ValueError:
            fail(interp, "ValueError", "invalid integer string %s" % interp.inspect(value))
    fail(interp, "TypeError", "cannot convert %s to Int" % interp.type_name(value))


def ctor_float(interp, args, node):
    arity(interp, args, "Float", 0, 1)
    if not args:
        return 0.0
    value = args[0]
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if is_num(value):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            fail(interp, "ValueError", "invalid float string %s" % interp.inspect(value))
    fail(interp, "TypeError", "cannot convert %s to Float" % interp.type_name(value))


def ctor_string(interp, args, node):
    arity(interp, args, "String", 0, 1)
    if not args:
        return ""
    return interp.to_s(args[0])


def ctor_bool(interp, args, node):
    arity(interp, args, "Bool", 0, 1)
    if not args:
        return False
    return truthy(args[0])


def ctor_list(interp, args, node):
    arity(interp, args, "List", 0, 1)
    if not args:
        return []
    return to_list(interp, args[0])


def ctor_map(interp, args, node):
    arity(interp, args, "Map", 0, 1)
    if not args:
        return {}
    value = args[0]
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        out = {}
        for item in value:
            if not isinstance(item, list) or len(item) != 2:
                fail(interp, "TypeError", "Map() expects a list of [key, value] pairs")
            out[item[0]] = item[1]
        return out
    fail(interp, "TypeError", "cannot convert %s to Map" % interp.type_name(value))


def ctor_range(interp, args, node):
    arity(interp, args, "Range", 2, 3)
    start = want_num(interp, args[0], "start")
    end = want_num(interp, args[1], "end")
    inclusive = True
    if len(args) > 2:
        inclusive = truthy(args[2])
    return TapoRange(start, end, inclusive)


def ctor_nil(interp, args, node):
    arity(interp, args, "Nil", 0)
    return None


# ---------------------------------------------------------------------------
# global functions
# ---------------------------------------------------------------------------
def fn_print(interp, args):
    _sys.stdout.write(" ".join(interp.to_s(arg) for arg in args))
    _sys.stdout.flush()
    return None


def fn_println(interp, args):
    _sys.stdout.write(" ".join(interp.to_s(arg) for arg in args) + "\n")
    _sys.stdout.flush()
    return None


def fn_p(interp, args):
    _sys.stdout.write(" ".join(interp.inspect(arg) for arg in args) + "\n")
    _sys.stdout.flush()
    return None


def fn_input(interp, args):
    arity(interp, args, "input", 0, 1)
    prompt = "" if not args else interp.to_s(args[0])
    if prompt:
        _sys.stdout.write(prompt)
        _sys.stdout.flush()
    line = _sys.stdin.readline()
    if line == "":
        return None
    return line.rstrip("\n")


def fn_len(interp, args):
    arity(interp, args, "len", 1)
    return size_of(interp, args[0])


def fn_str(interp, args):
    arity(interp, args, "str", 1)
    return interp.to_s(args[0])


def fn_int(interp, args):
    return ctor_int(interp, args, getattr(interp, "_builtin_node", None))


def fn_float(interp, args):
    return ctor_float(interp, args, getattr(interp, "_builtin_node", None))


def fn_bool(interp, args):
    return ctor_bool(interp, args, getattr(interp, "_builtin_node", None))


def fn_list(interp, args):
    return ctor_list(interp, args, getattr(interp, "_builtin_node", None))


def fn_type(interp, args):
    arity(interp, args, "type", 1)
    return interp.class_of(args[0])


def fn_type_name(interp, args):
    arity(interp, args, "type_name", 1)
    return interp.type_name(args[0])


def fn_inspect(interp, args):
    arity(interp, args, "inspect", 1)
    return interp.inspect(args[0])


def fn_assert(interp, args):
    arity(interp, args, "assert", 1, 2)
    if not truthy(args[0]):
        message = "assertion failed" if len(args) == 1 else interp.to_s(args[1])
        fail(interp, "AssertionError", message)
    return None


def fn_assert_eq(interp, args):
    arity(interp, args, "assert_eq", 2, 3)
    if not interp.tapo_equals(args[0], args[1]):
        message = "expected %s, got %s" % (interp.inspect(args[1]), interp.inspect(args[0]))
        if len(args) > 2:
            message = interp.to_s(args[2]) + ": " + message
        fail(interp, "AssertionError", message)
    return None


def fn_assert_ne(interp, args):
    arity(interp, args, "assert_ne", 2, 3)
    if interp.tapo_equals(args[0], args[1]):
        message = "expected values to differ, both are %s" % interp.inspect(args[0])
        if len(args) > 2:
            message = interp.to_s(args[2]) + ": " + message
        fail(interp, "AssertionError", message)
    return None


def fn_assert_raises(interp, args):
    arity(interp, args, "assert_raises", 1, 2)
    expected = None
    fn = args[0]
    if len(args) == 2:
        expected = args[0]
        fn = args[1]
        if not isinstance(expected, TapoClass):
            fail(interp, "TypeError", "assert_raises expects an error class")
    try:
        call(interp, fn, [])
    except Exception as exc:
        from .errors import TapoException

        if not isinstance(exc, TapoException):
            raise
        if expected is not None and not exc.value.klass.is_subclass_of(expected):
            fail(
                interp,
                "AssertionError",
                "expected %s, got %s: %s"
                % (expected.name, exc.value.klass.name, exc.value.fields.get("message", "")),
            )
        return exc.value
    wanted = expected.name if expected is not None else "an error"
    fail(interp, "AssertionError", "expected %s to be raised, but nothing was raised" % wanted)


def fn_test(interp, args):
    arity(interp, args, "test", 2)
    name = want_str(interp, args[0], "test name")
    fn = args[1]
    from .errors import TapoException

    try:
        call(interp, fn, [])
        interp.test_results.append({"name": name, "ok": True, "error": None})
    except TapoException as exc:
        interp.test_results.append({"name": name, "ok": False, "error": exc.value, "trace": exc.trace})
    return None


def fn_panic(interp, args):
    arity(interp, args, "panic", 1)
    fail(interp, "RuntimeError", interp.to_s(args[0]))


def fn_exit(interp, args):
    arity(interp, args, "exit", 0, 1)
    from .errors import TapoExit

    code = 0 if not args else want_int(interp, args[0], "code")
    raise TapoExit(code)


def fn_sleep(interp, args):
    arity(interp, args, "sleep", 1)
    seconds = want_num(interp, args[0], "seconds")
    if seconds < 0:
        fail(interp, "ValueError", "sleep duration cannot be negative")
    _time.sleep(seconds)
    return None


def fn_clock(interp, args):
    arity(interp, args, "clock", 0)
    return _time.time()


def fn_range(interp, args):
    arity(interp, args, "range", 1, 3)
    if len(args) == 1:
        stop = want_num(interp, args[0], "stop")
        return TapoRange(0, stop - 1, True)
    start = want_num(interp, args[0], "start")
    stop = want_num(interp, args[1], "stop")
    if len(args) == 2:
        return TapoRange(start, stop - 1, True)
    step = want_num(interp, args[2], "step")
    if step == 0:
        fail(interp, "ValueError", "range step cannot be zero")
    values = []
    current = start
    if step > 0:
        while current < stop:
            values.append(current)
            current += step
    else:
        while current > stop:
            values.append(current)
            current += step
    return values


def fn_enumerate(interp, args):
    arity(interp, args, "enumerate", 1, 2)
    items = to_list(interp, args[0])
    start = 0 if len(args) == 1 else want_int(interp, args[1], "start")
    return [[start + index, item] for index, item in enumerate(items)]


def fn_zip(interp, args):
    arity(interp, args, "zip", 2)
    left = to_list(interp, args[0])
    right = to_list(interp, args[1])
    return [[left[i], right[i]] for i in range(min(len(left), len(right)))]


def fn_sum(interp, args):
    arity(interp, args, "sum", 1, 2)
    items = to_list(interp, args[0])
    acc = 0 if len(args) == 1 else args[1]
    for item in items:
        acc = interp.binary_op("+", acc, item)
    return acc


def fn_min(interp, args):
    if not args:
        fail(interp, "ArgumentError", "min expects at least 1 argument, got 0")
    items = args[0] if len(args) == 1 and isinstance(args[0], list) else list(args)
    if not items:
        return None
    best = items[0]
    for item in items[1:]:
        if interp.compare_values(item, best) < 0:
            best = item
    return best


def fn_max(interp, args):
    if not args:
        fail(interp, "ArgumentError", "max expects at least 1 argument, got 0")
    items = args[0] if len(args) == 1 and isinstance(args[0], list) else list(args)
    if not items:
        return None
    best = items[0]
    for item in items[1:]:
        if interp.compare_values(item, best) > 0:
            best = item
    return best


def fn_sorted(interp, args):
    arity(interp, args, "sorted", 1, 2)
    items = to_list(interp, args[0])
    if len(args) == 1:
        return sorted(items, key=functools.cmp_to_key(lambda a, b: interp.compare_values(a, b)))
    return sorted(items, key=functools.cmp_to_key(lambda a, b: compare_with(interp, args[1], a, b)))


# ---------------------------------------------------------------------------
# standard modules
# ---------------------------------------------------------------------------
def make_module(name, attrs):
    return TapoModule(name, "<builtin:%s>" % name, attrs)


def build_math(interp):
    def unary(name, fn):
        def method(interp_, args):
            arity(interp_, args, name, 1)
            value = want_num(interp_, args[0], name)
            try:
                return fn(value)
            except ValueError as exc:
                fail(interp_, "ValueError", str(exc))

        return TapoBuiltin(name, method)

    def binary(name, fn):
        def method(interp_, args):
            arity(interp_, args, name, 2)
            a = want_num(interp_, args[0], name)
            b = want_num(interp_, args[1], name)
            try:
                return fn(a, b)
            except ValueError as exc:
                fail(interp_, "ValueError", str(exc))

        return TapoBuiltin(name, method)

    attrs = {
        "PI": _math.pi,
        "E": _math.e,
        "TAU": _math.tau,
        "INF": _math.inf,
        "NAN": _math.nan,
        "sqrt": unary("sqrt", _math.sqrt),
        "cbrt": unary("cbrt", lambda x: _math.copysign(abs(x) ** (1.0 / 3.0), x)),
        "sin": unary("sin", _math.sin),
        "cos": unary("cos", _math.cos),
        "tan": unary("tan", _math.tan),
        "asin": unary("asin", _math.asin),
        "acos": unary("acos", _math.acos),
        "atan": unary("atan", _math.atan),
        "atan2": binary("atan2", _math.atan2),
        "log": unary("log", _math.log),
        "log2": unary("log2", _math.log2),
        "log10": unary("log10", _math.log10),
        "exp": unary("exp", _math.exp),
        "pow": binary("pow", _math.pow),
        "floor": unary("floor", _math.floor),
        "ceil": unary("ceil", _math.ceil),
        "hypot": binary("hypot", _math.hypot),
        "degrees": unary("degrees", _math.degrees),
        "radians": unary("radians", _math.radians),
        "is_nan": unary("is_nan", _math.isnan),
        "is_inf": unary("is_inf", _math.isinf),
        "is_finite": unary("is_finite", _math.isfinite),
    }
    return make_module("math", attrs)


def build_json(interp):
    def to_jsonable(value, seen=None):
        if seen is None:
            seen = set()
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, list):
            ident = id(value)
            if ident in seen:
                fail(interp, "ValueError", "cannot serialize a cyclic list")
            seen.add(ident)
            try:
                return [to_jsonable(item, seen) for item in value]
            finally:
                seen.remove(ident)
        if isinstance(value, dict):
            ident = id(value)
            if ident in seen:
                fail(interp, "ValueError", "cannot serialize a cyclic map")
            seen.add(ident)
            try:
                return {interp.to_s(key): to_jsonable(item, seen) for key, item in value.items()}
            finally:
                seen.remove(ident)
        if isinstance(value, TapoInstance):
            return {
                "__class__": value.klass.name,
                **{key: to_jsonable(item, seen) for key, item in value.fields.items()},
            }
        if isinstance(value, TapoRange):
            return [value.start, value.end]
        fail(interp, "TypeError", "cannot serialize %s to JSON" % interp.type_name(value))

    def parse(interp_, args):
        arity(interp_, args, "JSON.parse", 1)
        text = want_str(interp_, args[0], "text")
        try:
            return _json.loads(text)
        except ValueError as exc:
            fail(interp_, "ValueError", "invalid JSON: %s" % exc)

    def stringify(interp_, args):
        arity(interp_, args, "JSON.stringify", 1, 2)
        pretty = len(args) > 1 and truthy(args[1])
        return _json.dumps(
            to_jsonable(args[0]),
            ensure_ascii=False,
            indent=2 if pretty else None,
        )

    return make_module(
        "json",
        {
            "parse": TapoBuiltin("JSON.parse", parse),
            "stringify": TapoBuiltin("JSON.stringify", stringify),
            "pretty": TapoBuiltin("JSON.pretty", lambda i, a: stringify(i, [a[0], True]) if len(a) == 1 else stringify(i, a)),
        },
    )


def build_fs(interp):
    def wrap_io(name, fn):
        def method(interp_, args):
            try:
                return fn(interp_, args)
            except OSError as exc:
                fail(interp_, "IOError", "%s: %s" % (name, exc.strerror or str(exc)))

        return TapoBuiltin("FS." + name, method)

    def read(interp_, args):
        arity(interp_, args, "FS.read", 1)
        path = want_str(interp_, args[0], "path")
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def write(interp_, args):
        arity(interp_, args, "FS.write", 2)
        path = want_str(interp_, args[0], "path")
        content = want_str(interp_, args[1], "content")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return len(content)

    def append(interp_, args):
        arity(interp_, args, "FS.append", 2)
        path = want_str(interp_, args[0], "path")
        content = want_str(interp_, args[1], "content")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(content)
        return len(content)

    def exists(interp_, args):
        arity(interp_, args, "FS.exists?", 1)
        return os.path.exists(want_str(interp_, args[0], "path"))

    def is_file(interp_, args):
        arity(interp_, args, "FS.is_file?", 1)
        return os.path.isfile(want_str(interp_, args[0], "path"))

    def is_dir(interp_, args):
        arity(interp_, args, "FS.is_dir?", 1)
        return os.path.isdir(want_str(interp_, args[0], "path"))

    def list_dir(interp_, args):
        arity(interp_, args, "FS.list", 1)
        path = want_str(interp_, args[0], "path")
        return sorted(os.listdir(path))

    def remove(interp_, args):
        arity(interp_, args, "FS.remove", 1)
        path = want_str(interp_, args[0], "path")
        if os.path.isdir(path) and not os.path.islink(path):
            os.rmdir(path)
        else:
            os.remove(path)
        return True

    def mkdir(interp_, args):
        arity(interp_, args, "FS.mkdir", 1, 2)
        path = want_str(interp_, args[0], "path")
        parents = len(args) > 1 and truthy(args[1])
        if parents:
            os.makedirs(path, exist_ok=True)
        else:
            os.mkdir(path)
        return True

    def join(interp_, args):
        arity(interp_, args, "FS.join", 1, 32)
        parts = [want_str(interp_, arg, "path part") for arg in args]
        return os.path.join(*parts)

    def size(interp_, args):
        arity(interp_, args, "FS.size", 1)
        return os.path.getsize(want_str(interp_, args[0], "path"))

    def read_lines(interp_, args):
        arity(interp_, args, "FS.read_lines", 1)
        with open(want_str(interp_, args[0], "path"), "r", encoding="utf-8") as handle:
            return handle.read().splitlines()

    def write_lines(interp_, args):
        arity(interp_, args, "FS.write_lines", 2)
        path = want_str(interp_, args[0], "path")
        lines = to_list(interp_, args[1])
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(interp_.to_s(line) for line in lines))
            handle.write("\n")
        return len(lines)

    attrs = {
        "read": wrap_io("read", read),
        "write": wrap_io("write", write),
        "append": wrap_io("append", append),
        "exists?": wrap_io("exists?", exists),
        "is_file?": wrap_io("is_file?", is_file),
        "is_dir?": wrap_io("is_dir?", is_dir),
        "list": wrap_io("list", list_dir),
        "remove": wrap_io("remove", remove),
        "mkdir": wrap_io("mkdir", mkdir),
        "join": TapoBuiltin("FS.join", join),
        "basename": TapoBuiltin("FS.basename", lambda i, a: os.path.basename(want_str(i, a[0], "path")) if len(a) == 1 else None),
        "dirname": TapoBuiltin("FS.dirname", lambda i, a: os.path.dirname(want_str(i, a[0], "path")) if len(a) == 1 else None),
        "extname": TapoBuiltin("FS.extname", lambda i, a: os.path.splitext(want_str(i, a[0], "path"))[1] if len(a) == 1 else None),
        "cwd": TapoBuiltin("FS.cwd", lambda i, a: os.getcwd()),
        "size": wrap_io("size", size),
        "read_lines": wrap_io("read_lines", read_lines),
        "write_lines": wrap_io("write_lines", write_lines),
    }
    return make_module("fs", attrs)


def build_time(interp):
    def now(interp_, args):
        arity(interp_, args, "Time.now", 0)
        return _time.time()

    def sleep(interp_, args):
        arity(interp_, args, "Time.sleep", 1)
        _time.sleep(want_num(interp_, args[0], "seconds"))
        return None

    def format_time(interp_, args):
        arity(interp_, args, "Time.format", 1, 2)
        stamp = args[0] if is_num(args[0]) else _time.time()
        pattern = "%Y-%m-%d %H:%M:%S" if len(args) == 1 else want_str(interp_, args[1], "format")
        if args and not is_num(args[0]):
            pattern = want_str(interp_, args[0], "format")
            stamp = _time.time()
        return _time.strftime(pattern, _time.localtime(stamp))

    def iso(interp_, args):
        arity(interp_, args, "Time.iso", 0, 1)
        stamp = _time.time() if not args else want_num(interp_, args[0], "timestamp")
        return _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime(stamp))

    return make_module(
        "time",
        {
            "now": TapoBuiltin("Time.now", now),
            "sleep": TapoBuiltin("Time.sleep", sleep),
            "format": TapoBuiltin("Time.format", format_time),
            "iso": TapoBuiltin("Time.iso", iso),
        },
    )


def build_regex(interp):
    def compile_pattern(interp_, pattern):
        try:
            return _re.compile(pattern)
        except _re.error as exc:
            fail(interp_, "ValueError", "invalid regular expression: %s" % exc)

    def match(interp_, args):
        arity(interp_, args, "Regex.match", 2)
        pattern = compile_pattern(interp_, want_str(interp_, args[0], "pattern"))
        text = want_str(interp_, args[1], "text")
        found = pattern.search(text)
        if found is None:
            return None
        return {
            "match": found.group(0),
            "groups": list(found.groups()),
            "start": found.start(),
            "end": found.end(),
            "captures": {key: value for key, value in found.groupdict().items()},
        }

    def test(interp_, args):
        arity(interp_, args, "Regex.test?", 2)
        pattern = compile_pattern(interp_, want_str(interp_, args[0], "pattern"))
        return pattern.search(want_str(interp_, args[1], "text")) is not None

    def find_all(interp_, args):
        arity(interp_, args, "Regex.find_all", 2)
        pattern = compile_pattern(interp_, want_str(interp_, args[0], "pattern"))
        return [found.group(0) for found in pattern.finditer(want_str(interp_, args[1], "text"))]

    def replace(interp_, args):
        arity(interp_, args, "Regex.replace", 3)
        pattern = compile_pattern(interp_, want_str(interp_, args[0], "pattern"))
        return pattern.sub(want_str(interp_, args[2], "replacement"), want_str(interp_, args[1], "text"))

    def split(interp_, args):
        arity(interp_, args, "Regex.split", 2)
        pattern = compile_pattern(interp_, want_str(interp_, args[0], "pattern"))
        return pattern.split(want_str(interp_, args[1], "text"))

    return make_module(
        "regex",
        {
            "match": TapoBuiltin("Regex.match", match),
            "test?": TapoBuiltin("Regex.test?", test),
            "find_all": TapoBuiltin("Regex.find_all", find_all),
            "replace": TapoBuiltin("Regex.replace", replace),
            "split": TapoBuiltin("Regex.split", split),
        },
    )


def build_random(interp):
    def seed(interp_, args):
        arity(interp_, args, "Random.seed", 1)
        _random.seed(want_int(interp_, args[0], "seed"))
        return None

    def rand(interp_, args):
        arity(interp_, args, "Random.random", 0)
        return _random.random()

    def rand_int(interp_, args):
        arity(interp_, args, "Random.int", 2)
        low = want_int(interp_, args[0], "low")
        high = want_int(interp_, args[1], "high")
        if low > high:
            low, high = high, low
        return _random.randint(low, high)

    def choice(interp_, args):
        arity(interp_, args, "Random.choice", 1)
        items = to_list(interp_, args[0])
        if not items:
            fail(interp_, "ValueError", "cannot choose from an empty list")
        return _random.choice(items)

    def shuffle(interp_, args):
        arity(interp_, args, "Random.shuffle", 1)
        items = want_list(interp_, args[0], "list")
        _random.shuffle(items)
        return items

    def sample(interp_, args):
        arity(interp_, args, "Random.sample", 2)
        items = to_list(interp_, args[0])
        count = want_int(interp_, args[1], "count")
        if count < 0 or count > len(items):
            fail(interp_, "ValueError", "sample size must be between 0 and the list size")
        return _random.sample(items, count)

    return make_module(
        "random",
        {
            "seed": TapoBuiltin("Random.seed", seed),
            "random": TapoBuiltin("Random.random", rand),
            "int": TapoBuiltin("Random.int", rand_int),
            "choice": TapoBuiltin("Random.choice", choice),
            "shuffle": TapoBuiltin("Random.shuffle", shuffle),
            "sample": TapoBuiltin("Random.sample", sample),
        },
    )


def build_sys(interp):
    def env(interp_, args):
        arity(interp_, args, "Sys.env", 1, 2)
        key = want_str(interp_, args[0], "key")
        if key in os.environ:
            return os.environ[key]
        return args[1] if len(args) > 1 else None

    def cwd(interp_, args):
        arity(interp_, args, "Sys.cwd", 0)
        return os.getcwd()

    def chdir(interp_, args):
        arity(interp_, args, "Sys.chdir", 1)
        os.chdir(want_str(interp_, args[0], "path"))
        return os.getcwd()

    def exit_(interp_, args):
        return fn_exit(interp_, args)

    attrs = {
        "version": VERSION,
        "platform": _sys.platform,
        "argv": list(interp.argv),
        "pid": os.getpid(),
        "home": os.path.expanduser("~"),
        "env": TapoBuiltin("Sys.env", env),
        "cwd": TapoBuiltin("Sys.cwd", cwd),
        "chdir": TapoBuiltin("Sys.chdir", chdir),
        "exit": TapoBuiltin("Sys.exit", exit_),
    }
    return make_module("sys", attrs)


# ---------------------------------------------------------------------------
# installation
# ---------------------------------------------------------------------------
def install(interp, env):
    # Builtin classes (Error hierarchy already exists).
    object_class = interp.error_classes["Object"]
    interp.Object = object_class
    int_class = TapoClass("Int", object_class, native=ctor_int, builtin=True)
    float_class = TapoClass("Float", object_class, native=ctor_float, builtin=True)
    string_class = TapoClass("String", object_class, native=ctor_string, builtin=True)
    bool_class = TapoClass("Bool", object_class, native=ctor_bool, builtin=True)
    list_class = TapoClass("List", object_class, native=ctor_list, builtin=True)
    map_class = TapoClass("Map", object_class, native=ctor_map, builtin=True)
    range_class = TapoClass("Range", object_class, native=ctor_range, builtin=True)
    generator_class = TapoClass("Generator", object_class, builtin=True)
    nil_class = TapoClass("Nil", object_class, native=ctor_nil, builtin=True)
    function_class = TapoClass("Function", object_class, builtin=True)
    class_class = TapoClass("Class", object_class, builtin=True)
    module_class = TapoClass("Module", object_class, builtin=True)
    aspect_class = TapoClass("Aspect", object_class, builtin=True)
    mixin_class = TapoClass("Mixin", object_class, builtin=True)
    interp.builtin_classes = {
        "Object": object_class,
        "Int": int_class,
        "Float": float_class,
        "String": string_class,
        "Bool": bool_class,
        "List": list_class,
        "Map": map_class,
        "Range": range_class,
        "Generator": generator_class,
        "Nil": nil_class,
        "Function": function_class,
        "Class": class_class,
        "Module": module_class,
        "Aspect": aspect_class,
        "Mixin": mixin_class,
    }
    interp.class_class = class_class
    interp.function_class = function_class

    for name, klass in interp.builtin_classes.items():
        env.define(name, klass, const=True)
    for name, klass in interp.error_classes.items():
        env.define(name, klass, const=True)

    env.define("VERSION", VERSION, const=True)
    env.define("AUTHOR", AUTHOR, const=True)
    env.define("LICENSE", LICENSE, const=True)
    env.define("argv", list(interp.argv), const=False)

    globals_map = {
        "print": fn_print,
        "println": fn_println,
        "puts": fn_println,
        "p": fn_p,
        "input": fn_input,
        "len": fn_len,
        "str": fn_str,
        "int": fn_int,
        "float": fn_float,
        "bool": fn_bool,
        "list": fn_list,
        "type": fn_type,
        "type_name": fn_type_name,
        "inspect": fn_inspect,
        "assert": fn_assert,
        "assert_eq": fn_assert_eq,
        "assert_ne": fn_assert_ne,
        "assert_raises": fn_assert_raises,
        "test": fn_test,
        "panic": fn_panic,
        "exit": fn_exit,
        "sleep": fn_sleep,
        "clock": fn_clock,
        "range": fn_range,
        "enumerate": fn_enumerate,
        "zip": fn_zip,
        "sum": fn_sum,
        "min": fn_min,
        "max": fn_max,
        "sorted": fn_sorted,
    }
    for name, fn in globals_map.items():
        env.define(name, TapoBuiltin(name, fn), const=True)

    env.define("math", build_math(interp), const=True)
    env.define("json", build_json(interp), const=True)
    env.define("fs", build_fs(interp), const=True)
    env.define("time", build_time(interp), const=True)
    env.define("regex", build_regex(interp), const=True)
    env.define("random", build_random(interp), const=True)
    env.define("sys", build_sys(interp), const=True)

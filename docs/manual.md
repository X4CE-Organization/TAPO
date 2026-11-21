# The TAPO Language Manual

Version 0.0.2 · © 2026 X4CE · MIT

TAPO is an expression-oriented, dynamically typed, object-oriented language. It is
implemented as a compact tree-walking interpreter in Python and ships with its
own standard library, test runner and REPL.

This manual describes the language as implemented. For the exhaustive list of
built-in methods, see [the standard library reference](stdlib.md).

---

## 1. Running TAPO

```bash
./tapo program.tapo          # run a file
./tapo -e 'println("hi")'  # evaluate an expression
./tapo repl                # interactive session
./tapo check program.tapo    # parse only
./tapo fmt program.tapo      # format in place
./tapo fmt --check .         # report files that would change
./tapo new demo              # scaffold a new project
./tapo test                # run tests/
```

`./tapo` is a launcher that sets `PYTHONPATH=src`. After `pip install -e .`, the
same commands are available as `tapo`. A program receives its command-line
arguments in the global list `argv`. `tapo fmt` uses two-space indentation,
normalises continuation lines, and preserves comments and string contents.

TAPO programs use the `.tapo` extension. Reusable library files use `.takg`; all
files in `std/` follow this convention. An import may spell the extension
explicitly (`import "std/test.takg"`) or omit it (`import "std/test"`); when the
extension is omitted, TAPO looks for `.takg` first and `.tapo` second.

---

## 2. Lexical structure

### Comments

```tapo
# a line comment

#= a block comment
   #= block comments nest =#
   still commented
=#
```

### Identifiers

Identifiers are Unicode-aware, so `let 名字 = "TAPO"` is valid. They may end in
`?` (predicate style) or `!` (mutating style):

```tapo
xs.empty?
map.merge!({b: 2})
```

### Literals

```tapo
nil
true
false
42
3.14
1e9
"hello"
"interpolated: #{1 + 2}"
'raw \n string'          # single quotes do not interpolate
"""multi
line"""
[1, 2, 3]
{a: 1, "b": 2}
1..5                     # inclusive range
1...5                    # exclusive range
```

Double-quoted strings interpolate `#{ expression }`. A hash sign followed by
`{` starts an interpolation; use `\#{` for a literal `#{`.

### Statement separators

Newlines separate expressions. Semicolons may be used instead. Newlines inside
`(...)` and `[...]` are ignored; inside `{...}` they remain significant (so
blocks can contain several statements). A newline before a leading `|>` is
treated as a continuation.

---

## 3. Values and truthiness

Everything is an object. The built-in classes are:

`Object`, `Int`, `Float`, `String`, `Bool`, `List`, `Map`, `Range`, `Nil`,
`Function`, `Class`, `Module`, `Aspect`, `Mixin`, and the error classes.

Only `nil` and `false` are falsey. **Zero and the empty string are truthy.**

```tapo
if 0 { println("0 is truthy") }
```

`class_of(x)` is available as `x.class`; `type_name(x)` is the global helper.

---

## 4. Variables and assignment

```tapo
let answer = 42          # constant binding
var count = 0            # mutable binding

count = 1
count += 1
count -= 1
count *= 2
count /= 2
count //= 2
count %= 3
count **= 2
count |= 1
count &= 7
count ^= 3
count <<= 1
count >>= 1
count ??= 5              # assign only when currently nil
```

Assigning to a `let` raises `FrozenError`. Assigning to an undeclared name
raises `NameError`.

Destructuring works with lists, maps and class patterns:

```tapo
let [first, second, ...rest] = [1, 2, 3, 4]
let {x, y} = {x: 1, y: 2}
let Point(px, py) = Point(1, 2)
```

Pattern declarations are described in §11.

---

## 5. Operators

From low to high precedence:

| Operators | Meaning |
| --- | --- |
| `=` and compound assignments | assignment |
| `\|>` | pipeline |
| `??` | nil coalescing |
| `or`, `\|\|` | logical or (short-circuit) |
| `and`, `&&` | logical and (short-circuit) |
| `==`, `!=` | equality |
| `<`, `<=`, `>`, `>=`, `in`, `is` | comparison, membership, type test |
| `..`, `...` | range construction |
| `\|` | bitwise or |
| `^` | bitwise xor |
| `&` | bitwise and |
| `<<`, `>>` | shifts |
| `+`, `-` | addition, subtraction |
| `*`, `/`, `//`, `%` | multiplication, division, floor division, modulo |
| `**` | exponentiation (right-associative) |
| unary `-`, `+`, `!`, `~`, `not` | unary operators |

Notes:

- `/` is true division; `//` floors.
- `%` on strings is printf-style formatting: `"%s = %d" % ["x", 3]`.
- `in` tests membership in strings, lists, maps (keys), ranges and objects that
  define `contains`.
- `is` tests the class of a value: `x is Int`, `p is Point`.
- `-5.abs()` parses as `-(5.abs())`; write `(-5).abs()`.

Ranges are inclusive with `..` and exclusive with `...`. A descending range
iterates downward automatically:

```tapo
(1..5).to_list()    # [1, 2, 3, 4, 5]
(1...5).to_list()   # [1, 2, 3, 4]
(5..1).to_list()    # [5, 4, 3, 2, 1]
```

---

## 6. Control flow

`if` is an expression; `else` is optional:

```tapo
let label = if score >= 60 { "pass" } else { "fail" }
```

`unless` is the negated form:

```tapo
unless done { println("working") }
```

`while` and `until`:

```tapo
while n < 10 { n += 1 }
until n == 0 { n -= 1 }
```

`for` iterates any iterable (lists, strings, maps, ranges, or objects with an
`each` method):

```tapo
for item in [1, 2, 3] { println(item) }
for [key, value] in {a: 1} { println("#{key}=#{value}") }
for i in 1..3 { println(i) }
```

`loop` repeats forever:

```tapo
loop {
  break if done
}
```

`break` and `continue` work in `for`, `while`, `until` and `loop`.

Blocks are expressions and return their last value:

```tapo
let x = { let a = 1; a + 2 }   # 3
```

---

## 7. Functions

Named functions:

```tapo
fn add(a, b) => a + b

fn greet(name = "world") {
  "hello, #{name}"
}
```

Anonymous functions are written the same way without a name:

```tapo
let double = fn(x) => x * 2
let apply = fn(f, x) { f(x) }
```

Parameters may have defaults and a final rest parameter:

```tapo
fn log(level, ...parts) => println(level, parts.join(" "))
fn greet(name = "world") => "hello #{name}"
```

Default expressions are evaluated at call time. Call with a splat:

```tapo
let args = [1, 2]
add(...args)
```

Functions are closures. `return` exits early; `return` with no value returns
`nil`.

`fn` methods are covered in §8.

### Generators

A function that contains `yield` returns a lazy generator instead of running
its body immediately:

```tapo
fn count(limit) {
  var i = 0
  while i < limit {
    yield i
    i += 1
  }
}

let numbers = count(3)
println(numbers.next())   # 0
println(numbers.next())   # 1
println(numbers.to_list()) # [2]
```

Generators work with `for`, and provide `next`, `done?`, `each`, `to_list`,
`take` and `close`. `close` runs any `finally` blocks in the generator. When a
generator is exhausted, `next` raises `StopIteration`.

### Defer

`defer { ... }` registers cleanup for the current block. Deferred blocks run in
reverse registration order when the block exits, including `return`, `break`
and exceptions:

```tapo
fn work() {
  defer { println("second") }
  defer { println("first") }
  println("body")
}
```

Each block has its own defer stack. A deferred block that raises replaces the
original exception, as in `finally` blocks.

---

## 8. Classes and objects

```tapo
class Point {
  var x = 0, y = 0

  init(x, y) {
    self.x = x
    self.y = y
  }

  fn +(other) => Point(x + other.x, y + other.y)
  fn to_s() => "Point(#{x}, #{y})"
}
```

- `class Name { ... }` declares a class.
- `var x = 0, y = 0` declares instance fields with defaults.
- `init` is the constructor; calling `Point(1, 2)` constructs an instance.
- Methods may be written `fn name(...)` or bare `name(...)`.
- A class with no `init` accepts positional field values in declaration order.
- Unqualified names inside methods fall back to `self` attributes/methods.

### Inheritance and super

```tapo
class Animal {
  var name = "?"
  init(name) { self.name = name }
  fn speak() => "..."
}

class Dog < Animal {
  init(name) { super.init(name) }
  fn speak() => "woof"
}
```

`super.method(args)` calls the parent method. `super` alone is allowed only
where the current method name exists on the parent, e.g. `super()` inside
`init`.

### Getters, setters and statics

```tapo
class Counter {
  var n = 0
  get value { self.n }
  set value(v) { self.n = v }
  static fn make() => Counter()
}
```

`get value` is accessed as `counter.value` (no parentheses). `set value(v)` is
used by assignment. Both may also be written with `=> expression`.

### Operator overloading

Define a method named after the operator:

```tapo
class Vec {
  var x = 0, y = 0
  fn +(other) => Vec(x + other.x, y + other.y)
  fn ==(other) => x == other.x and y == other.y
}
```

Overloadable: `+ - * / // % ** == != < <= > >= & | ^ << >> ~`.
Indexing uses `get(i)` / `set(i, value)` or `[]`:

```tapo
class Box {
  var items = []
  fn get(i) => items[i]
  fn set(i, v) { items[i] = v }
}
box[0] = 10
```

### Callable objects and method_missing

If an object has a `call` method it can be invoked like a function. If a
missing method is called, TAPO looks for `method_missing(name, args)`:

```tapo
class Ghost {
  fn method_missing(name, args) => "missing #{name} #{args}"
}
```

### Class introspection

`Point.name`, `Point.superclass`, `Point.ancestors`, `Point.fields()`,
`Point.methods()`, `Point.statics()`, `Point.aspects()`.
`Point.new(...)` is equivalent to `Point(...)`. `Point.include(Mixin)` and
`Point.apply(Aspect)` mutate the class at runtime.

---

## 9. Mixins

```tapo
mixin Greeter {
  fn greet() => "hi from #{self.name}"
}

class Person with Greeter {
  var name = "?"
  init(name) { self.name = name }
}
```

A class may inherit from one superclass and include any number of mixins:

```tapo
class Child < Parent with A, B { ... }
```

Mixins contribute methods, getters, setters, statics and fields. Methods from
mixins can use `self` and `super`.

---

## 10. Enums

`enum` declares an algebraic data type. Each variant becomes a class, available
both globally and under the enum name:

```tapo
enum Shape {
  Circle(radius)
  Rect(width, height)
}

enum Color { Red, Green, Blue }

let shape = Circle(2)
println(shape)                 # Circle(2)
println(shape == Circle(2))    # true

match shape {
  Circle(r) => println("circle #{r}"),
  Rect(w, h) => println("rect #{w}x#{h}")
}
```

Variants with fields are constructed positionally or with a no-argument
constructor when they have no fields (`Red()`). Variant classes compare by
identity of the variant and equality of their fields. Patterns use the same
syntax as class patterns: `Circle(r)` or `Color.Red`.

---

## 11. Pattern matching

```tapo
let result = match value {
  0 => "zero"
  1 | 2 | 3 => "small"
  n if n < 0 => "negative"
  [first, ...rest] => "list: #{first}, rest #{rest}"
  {kind: "ok", value: v} => "ok: #{v}"
  Point(x: 0, y) => "on the y axis at #{y}"
  Point(x, y) => "point #{x}, #{y}"
  pair as [a, b] => "pair #{a}, #{b}"
  else => "other"
}
```

Patterns:

- literals: `nil`, `true`, `false`, numbers, strings;
- `_` matches anything without binding;
- a bare lower-case name binds;
- `1..5` / `6...9` match numeric ranges (inclusive / exclusive);
- `[a, b, ...rest]` matches lists and strings;
- `{key: pattern, ...rest}` matches maps;
- `Class(positional..., key: pattern)` matches instances;
- `p1 | p2` is an or-pattern;
- `pattern as name` binds the whole value;
- `else` is the wildcard arm.

Numeric range patterns only accept number literals as bounds for now. Class
patterns match by class and then by fields. Positional patterns bind
fields in declaration order, **skipping fields named by keyword patterns**.
Extra fields are ignored. A subclass instance matches a parent class pattern.
`Object(...)` matches any object.

Arms may be separated by newlines or commas. Guards are evaluated after the
pattern binds.

Destructuring declarations reuse the same patterns:

```tapo
let [a, b, ...rest] = [1, 2, 3, 4]
let {x, y} = {x: 1, y: 2}
let Point(x, y) = point
```

---

## 12. Pipelines

`|>` inserts the left value as the first argument:

```tapo
"hello" |> println
[1, 2, 3] |> sum
[1, 2, 3] |> map(fn(x) => x * 2)
```

With a placeholder `_`, the right side is evaluated with `_` bound:

```tapo
1..20
  |> _.filter(fn(n) => n % 3 == 0)
  |> _.map(fn(n) => n * n)
  |> _.sum()
```

A newline before `|>` continues the pipeline.

---

## 13. Errors

```tapo
try {
  risky()
} catch err {
  println("failed: #{err.message}")
} finally {
  println("cleanup")
}
```

`try` is an expression. `catch` binds the error instance. `finally` always runs.
`raise value` throws; strings and other values are wrapped in `RuntimeError`.
The built-in hierarchy includes:

`Error`, `RuntimeError`, `ArgumentError`, `TypeError`, `NameError`,
`AttributeError`, `IndexError`, `KeyError`, `ValueError`,
`ZeroDivisionError`, `AssertionError`, `ImportError`, `IOError`,
`MatchError`, `NotImplementedError`, `FrozenError`.

Custom errors:

```tapo
class MyError < Error {}
raise MyError("custom message")
```

Error instances expose `message`, `trace`, `file` and `line`.

### Resource management with `with`

`with` guarantees that `close` is called when the block exits, whether it
returns normally, raises, returns, breaks or continues:

```tapo
class Timer {
  fn close() { println("closed") }
}

with Timer() as timer {
  println("working")
}

let value = with Timer() { 42 }   # with is also an expression
```

The resource must respond to `close`. The optional `as name` binding is a
constant inside the block.

---

## 14. Modules

Library modules are `.takg` files. Programs are `.tapo` files and are run directly,
not imported as libraries. An import may omit the extension; `.takg` is preferred
and `.tapo` remains accepted for compatibility.

```tapo
# math_helpers.takg
let _private = 1

fn square(x) => x * x

class Box { var value = 0 }
```

```tapo
import "./math_helpers.takg" as M
println(M.square(4))
println(M.Box(3).value)
```

All top-level names not starting with `_` are exported by default. Use
`export name` to export a private name, or `export` before a declaration. An
unaliased import binds each exported name directly:

```tapo
import "std/option.takg"
```

Modules are cached by real path; circular imports raise `ImportError`.
Built-in modules (`math`, `json`, `fs`, `time`, `regex`, `random`, `sys`) can be
imported by bare name:

```tapo
import "math" as math
println(math.sqrt(9))
```

Search order: directory of the importing file, current directory, `TAPO/std`, the
repository root, `$TAPO_PATH`, and the installed `share/tapo/std`. The importer's
own file is skipped, so a module named `functional.takg` can import
`"functional"` and resolve to `std/functional.takg` without resolving to itself.

### Extra libraries

TAPO ships optional `.takg` libraries for common tasks. They are independent: import
only the ones a file needs.

```tapo
import "std/strings.takg" as S
import "std/collections.takg" as C

println(S.camelize("hello_world"))
println(C.median([3, 1, 2]))
```

| Library | Purpose |
| --- | --- |
| `std/functional.takg` | Composition, memoisation, retry, small math helpers. |
| `std/strings.takg` | Naming, formatting, wrapping and HTML helpers. |
| `std/collections.takg` | Core collection helpers plus higher-level extras. |
| `std/result.takg` | Explicit `Result` / `Ok` / `Err` values. |
| `std/validation.takg` | Predicates and guard helpers. |
| `std/io.takg` | JSON/JSONL and filesystem conveniences. |
| `std/csv.takg` | RFC-style CSV parsing/stringifying and map conversion. |
| `std/path.takg` | Path splitting, extensions, suffixes and filesystem helpers. |
| `std/cli.takg` | Small command-line flag/option parser. |
| `std/base64.takg` | Base64/base64url, hex and URL encoding helpers. |
| `std/uuid.takg` | UUID v4/v5 generation and validation. |
| `std/ini.takg` | Small INI parser/stringifier. |
| `std/set.takg` | List-backed value set with union/intersection/difference. |
| `std/template.takg` | Minimal `{{name}}` template rendering. |

See [Extra libraries](libraries.md) for the full API.

---

## 15. The object protocol

These methods are available on every value:

| Method | Meaning |
| --- | --- |
| `class` | the value's class |
| `to_s()` | human-readable string |
| `inspect()` | debug representation |
| `nil?` | true for `nil` |
| `responds_to?(name)` | whether a method/field exists |
| `methods()` | method and field names |
| `send(name, args)` | dynamic dispatch |
| `is_a?(Class)` | instance of class or subclass |
| `instance_of?(Class)` | exact class |
| `equal?(other)` | identity |
| `hash()` | structural hash |
| `tap(fn)` | call fn with self, return self |
| `then(fn)` | call fn with self, return its result |
| `dup()` | shallow copy |

Custom iteration: define `each(fn)`; TAPO's `for`, `to_list`, `map`, etc. will use
it. Custom truth/equality/printing can be provided with `to_s`, `inspect`,
`==`, `contains`, `get`, `set`, `call`, `method_missing`.

---

## 16. Testing

```tapo
import "std/test.takg" as T

test("math", fn() {
  assert_eq(1 + 1, 2)
  assert(2 > 1)
  assert_raises(ZeroDivisionError, fn() { 1 // 0 })
  T.assert_includes([1, 2, 3], 2)
})
```

`tapo test` discovers `*_test.tapo` files. Each `test(name, fn)` records a result;
assertions raise `AssertionError`. Use `T.assert_close(a, b)` for floats,
`T.assert_match(pattern, text)` for regexes, and `T.assert_type(value, Class)`.

---

## 17. REPL

```bash
./tapo repl
```

The REPL keeps one environment across lines, supports multi-line blocks by
bracket balance, and provides `:help`, `:vars`, `:quit`. Expressions are
printed with `inspect`.

---

## 18. Limits and current behaviour

- Single inheritance; multiple mixins.
- Dynamic typing with runtime checks.
- Tree-walking interpreter: clarity over speed.
- `after` advice runs for its side effects; its return value is ignored.
  Use `around` to transform a result.
- Unaliased imports do not overwrite an existing binding of the same name.
- Map dot access (`m.key`) only reads or writes an existing string key; use
  `m[key] = value` to add a new key.
- `-x.method()` binds as `-(x.method())`; parenthesise negative receivers.
- Range patterns require numeric literal bounds.
- `defer` is block-scoped and runs in LIFO order.

# TAPO

**TAPO** is a small, expressive, object-oriented programming language with
first-class aspects, pattern matching, pipelines, mixins and a batteries-included
standard library. It runs on Python 3.9+ with **zero third-party dependencies**.

```
TAPO 0.0.2  ·  © 2026 X4CE  ·  MIT
```

TAPO is deliberately readable: the lexer, parser, object model, interpreter and
standard library are all plain Python and small enough to explore in an
afternoon. The language itself is expression-oriented — almost everything
returns a value.

TAPO programs use the `.tapo` extension. Reusable library modules use `.takg`; the
whole standard library is written as `.takg` files. Imports may
omit the extension, in which case `.takg` is tried before `.tapo`.

---

## Quick start

```bash
cd TAPO
./tapo examples/hello.tapo
./tapo test
```

Or install the `tapo` command:

```bash
python3 -m pip install -e .
tapo version
```

The repository also works without installing anything:

```bash
PYTHONPATH=src python3 -m tapo examples/hello.tapo
```

---

## A taste of TAPO

```tapo
class Point {
  var x = 0, y = 0
  init(x, y) { self.x = x; self.y = y }

  fn +(other) => Point(x + other.x, y + other.y)
  fn to_s() => "Point(#{x}, #{y})"
}

class LoudPoint < Point {
  fn to_s() => super.to_s().upper()
}

let p = Point(1, 2) + Point(3, 4)
println(p)                    # Point(4, 6)
println(LoudPoint(1, 2))      # POINT(1, 2)

let answer = 1..20
  |> _.filter(fn(n) => n % 3 == 0)
  |> _.map(fn(n) => n * n)
  |> _.sum()

println(answer)               # 819
```

### Aspects (AOP)

```tapo
aspect Logging {
  before * (self, method, args) {
    println("-> #{method}(#{args.join(", ")})")
  }
  after * (self, method, args, result) {
    println("<- #{method} = #{result}")
  }
}

class Calculator {
  use Logging
  fn add(a, b) => a + b
}

Calculator().add(2, 3)
```

`after` advice is for side effects. Use `around` when you want to replace or
transform the result:

```tapo
aspect Cached {
  around slow (self, method, args, proceed) {
    proceed(args) * 2
  }
}
```

### Patterns

```tapo
match value {
  0 => "zero"
  n if n is Int and n < 0 => "negative"
  [first, ...rest] => "list starting with #{first}"
  {kind: "ok", value: v} => "ok: #{v}"
  Point(x: 0, y) => "on the y axis at #{y}"
  Point(x, y) => "point (#{x}, #{y})"
  else => "something else"
}
```

---

## Feature highlights

- **Expression-oriented**: blocks, `if`, `try`, `match` and assignments are values.
- **OOP**: classes, single inheritance, `super`, mixins, getters/setters, statics,
  operator overloading, index protocol, `method_missing`, callable objects.
- **AOP**: `before` / `after` / `around` advice, wildcard selectors, `proceed`,
  aspect application at class definition or at runtime.
- **Pattern matching**: literals, numeric ranges (`1..5`, `6...9`), lists, maps,
  class destructuring, guards, or-patterns, `as` bindings, rest patterns.
- **Algebraic enums**: `enum Shape { Circle(r), Rect(w, h) }`; variants are
  classes and participate in pattern matching.
- **Generators**: `yield` produces lazy sequences with `next`, `to_list`,
  `take`, `for` and automatic cleanup via `close`.
- **Deferred cleanup**: `defer { ... }` runs at block exit in LIFO order, on
  normal completion, `return`, `break` and errors.
- **Resource management**: `with resource as name { ... }` always calls
  `close`, including on errors, returns and breaks.
- **Formatter**: `tapo fmt` normalises indentation and continuation lines while
  preserving comments and string contents; `--check` is CI-friendly.
- **Pipelines**: `x |> f`, `x |> f(a)`, and `x |> _.method()` placeholders.
- **Modules**: file modules, explicit and default exports, private `_names`,
  built-in modules, circular-import detection.
- **Errors**: exception hierarchy, `try`/`catch`/`finally`, `raise`, source traces.
- **Rich built-ins**: strings, lists, maps, ranges, math, JSON, filesystem,
  time, regex, random, system info, Base64/hex/URL encoding, hashing and UUIDs.
- **Extra libraries**: independent, optional `.takg` libraries for functional
  helpers (`std/functional.takg`), strings (`std/strings.takg`), collection extras
  (`std/collections.takg`), `Result` (`std/result.takg`), validation
  (`std/validation.takg`), JSON/JSONL/filesystem I/O (`std/io.takg`), CSV
  (`std/csv.takg`), path manipulation (`std/path.takg`), CLI argument parsing
  (`std/cli.takg`), Base64/UUID (`std/base64.takg`, `std/uuid.takg`), INI config
  (`std/ini.takg`), sets (`std/set.takg`) and templates (`std/template.takg`).
- **Test runner**: `tapo test`, `test(...)`, assertions and a small stdlib test kit.
- **REPL and tooling**: interactive REPL, `check`, `-e`, VS Code grammar/snippets.

---

## CLI

| Command | Description |
| --- | --- |
| `tapo file.tapo [args...]` | Run a program. Arguments appear in `argv`. |
| `tapo run file.tapo` | Same as above, explicit form. |
| `tapo repl` | Start the interactive REPL. |
| `tapo test [paths...]` | Run `*_test.tapo` files (default `tests/`). |
| `tapo check file` | Parse a `.tapo` program or `.takg` library without executing it. |
| `tapo fmt [--check] [paths...]` | Format sources in place; `--check` reports files that would change. |
| `tapo new <name>` | Create a small project scaffold (`src/main.tapo`, `tests/`). |
| `tapo -e 'code'` | Evaluate a one-liner. |
| `tapo version` | Show the version banner. |
| `tapo help` | Show usage. |

REPL commands: `:help`, `:vars`, `:quit`.

---

## Project layout

```
TAPO/
├── tapo                 # runnable launcher (PYTHONPATH=src)
├── src/tapo/            # lexer, parser, AST, interpreter, objects, builtins, formatter, CLI
├── std/               # .takg library modules
├── tests/             # language and standard-library tests
├── examples/          # runnable example programs
├── docs/              # manual, standard library and build notes
├── editors/vscode/    # syntax highlighting, snippets and language config
├── pyproject.toml
└── LICENSE
```

---

## Testing

```bash
./tapo test
```

The runner discovers every `*_test.tapo` under the given paths. A test file uses
the tiny test kit:

```tapo
import "std/test.takg" as T

test("addition", fn() {
  assert_eq(1 + 1, 2)
  T.assert_includes([1, 2, 3], 2)
})
```

Assertion failures are collected per test; syntax/runtime file errors are
reported separately. Exit code is non-zero if anything failed.

Formatter regression tests are plain Python:

```bash
PYTHONPATH=src python3 tests/formatter_test.py
```

---

## Documentation

- [Language manual](docs/manual.md) — the full language tour and reference.
- [Standard library](docs/stdlib.md) — built-in methods, globals and modules.
- [Extra libraries](docs/libraries.md) — optional functional, string,
  collection, result, validation, I/O, CSV, path and CLI libraries.
- [Examples](examples/) — runnable programs.
- [Building executables](docs/build.md) — macOS, Linux and Windows packaging.
- [VS Code extension](editors/vscode/README.md) — local syntax support.

---

## Design notes

TAPO is a tree-walking interpreter. It favours:

1. **Small implementation** over maximum speed.
2. **Readable semantics** over clever hidden magic (though aspects are the
   language's deliberate bit of magic).
3. **Good error messages** with file, line, column and a source caret.
4. **Everything is an object**: numbers, strings, lists, maps, ranges, classes,
   functions, modules and aspects all respond to methods.

Only `nil` and `false` are falsey.

---

## License

MIT © 2026 X4CE. See [LICENSE](LICENSE).

# TAPO Standard Library

All library modules use the `.takg` extension. Programs that use them remain
`.tapo` files.

Version 0.0.2 · © 2026 X4CE · MIT

This is the reference for TAPO's built-in methods, global functions, modules and
the TAPO-level library in `std/`.

Conventions:

- Methods marked with `?` are predicates and return `true`/`false`.
- Methods marked with `!` mutate the receiver.
- Collection callbacks are ordinary TAPO functions/lambdas.
- `list.each(fn)` calls `fn(item)`; `map.each(fn)` calls `fn([key, value])`.
- `map.map(fn)` and `map.filter(fn)` call `fn(key, value)` with two arguments.
- `reduce(fn)` uses the first element as the accumulator; `reduce(init, fn)`
  starts from `init`.
- Ranges may be ascending or descending; `..` includes the endpoint and `...`
  excludes it.

---

## Global functions

| Function | Description |
| --- | --- |
| `print(...)` | Print values separated by spaces, without a newline. |
| `println(...)` / `puts(...)` | Print values separated by spaces, with a newline. |
| `p(...)` | Print `inspect` representations, with a newline. |
| `input(prompt = "")` | Read a line from stdin; `nil` at EOF. |
| `len(value)` | Size of a string, list, map or range. |
| `str(value)` | Convert to a string (`to_s`). |
| `int(value)` | Convert to an integer. |
| `float(value)` | Convert to a float. |
| `bool(value)` | TAPO truthiness (`nil`/`false` are false). |
| `list(iterable)` | Convert an iterable to a list. |
| `type(value)` | The value's class. |
| `type_name(value)` | The class name as a string. |
| `inspect(value)` | Debug representation. |
| `assert(cond, message = "assertion failed")` | Raise `AssertionError` if false. |
| `assert_eq(actual, expected, message = nil)` | Assert equality. |
| `assert_ne(actual, expected, message = nil)` | Assert inequality. |
| `assert_raises(ErrorClass?, fn)` | Run fn, assert it raises; returns the error. |
| `test(name, fn)` | Register a test result (used by `tapo test`). |
| `panic(message)` | Raise `RuntimeError`. |
| `exit(code = 0)` | Exit the process. |
| `sleep(seconds)` | Sleep. |
| `clock()` | Unix time as a float. |
| `range(...)` | `range(stop)`, `range(start, stop)`, or `range(start, stop, step)`; returns a range/list. |
| `enumerate(iterable, start = 0)` | List of `[index, item]` pairs. |
| `zip(a, b)` | List of `[a_i, b_i]` pairs. |
| `sum(iterable, initial = 0)` | Sum via `+`. |
| `min(...)` / `max(...)` | Accepts multiple values or one iterable. |
| `sorted(iterable, comparator = nil)` | Sorted list; optional comparator function. |

Constants: `VERSION`, `AUTHOR`, `LICENSE`, `argv`.

---

## Object protocol

Available on every value (user classes may override `to_s`, `inspect`, `==`):

| Method | Description |
| --- | --- |
| `class` | The value's class. |
| `to_s()` | String form. |
| `inspect()` | Debug form. |
| `nil?` | True only for `nil`. |
| `responds_to?(name)` | Whether a method or field exists. |
| `methods()` | Method and field names. |
| `send(name, args = [])` | Dynamic dispatch. |
| `is_a?(Class)` | Class or subclass test. |
| `instance_of?(Class)` | Exact class test. |
| `equal?(other)` | Identity comparison. |
| `hash()` | Structural hash. |
| `tap(fn)` | Calls `fn(self)`, returns `self`. |
| `then(fn)` | Calls `fn(self)`, returns its result. |
| `dup()` | Shallow copy of a list, map or instance. |

---

## Int

`abs`, `to_f`, `to_i`, `to_s(base = 10)`, `times(fn)`, `upto(n, fn)`,
`downto(n, fn)`, `even?`, `odd?`, `zero?`, `positive?`, `negative?`,
`clamp(lo, hi)`, `digits(base = 10)`, `gcd(n)`, `lcm(n)`, `pow(n)`, `floor`,
`ceil`, `round`, `succ`, `pred`, `chr`, `bit_length`.

```tapo
3.times(fn(i) => println(i))
255.to_s(16)        # "ff"
```

Constructors: `Int()`, `Int("ff", 16)`, `Int(3.9)`.

---

## Float

`abs`, `floor`, `ceil`, `round(digits = nil)`, `to_i`, `to_f`, `truncate`,
`nan?`, `infinite?`, `finite?`, `sqrt`.

`Float.round()` returns an integer; `Float.round(n)` returns a float with `n`
decimal places.

Constructors: `Float()`, `Float("1.5")`, `Float(2)`.

---

## String

`size`, `length`, `empty?`, `blank?`, `upper`, `lower`, `upcase`, `downcase`,
`capitalize`, `title`, `swapcase`, `strip`, `trim`, `lstrip`, `rstrip`,
`split(sep = nil)`, `chars`, `bytes`, `lines`, `replace(old, new)`,
`contains(sub)`, `starts_with(prefix)`, `ends_with(suffix)`,
`index_of(sub, start = 0)`, `slice(start, length = nil)`, `substring`,
`reverse`, `repeat(n)`, `each_char(fn)`, `to_i(base = 10)`, `to_f`, `count(sub)`,
`center(width, pad = " ")`, `ljust(width, pad = " ")`, `rjust(width, pad = " ")`,
`zfill(width)`, `join(iterable)`, `ord`, `codepoints`.

```tapo
"  TAPO  ".trim()          # "TAPO"
"a,b,c".split(",")       # ["a", "b", "c"]
"hello".slice(1, 3)      # "ell"
"-".join(["a", "b"])     # "a-b"
```

Strings support `[]` indexing, ranges in `[]`, `+`, `*`, `in`, and `%`
formatting.

---

## List

`size`, `length`, `empty?`, `push(v)` / `append(v)`, `pop`, `shift`, `unshift(v)`,
`insert(index, v)`, `remove(v)` / `delete(v)`, `delete_at(index)`, `clear`,
`compact`, `first(n = nil)`, `last(n = nil)`, `take(n)`, `drop(n)`,
`each(fn)`, `each_with_index(fn)`, `map(fn)` / `collect(fn)`, `flat_map(fn)`,
`filter(fn)` / `select(fn)`, `reject(fn)`, `find(fn)`, `find_index(fn)`,
`any?(fn = nil)`, `all?(fn = nil)`, `none?(fn = nil)`, `count(value_or_fn)`,
`reduce(init_or_fn, fn = nil)`, `sum`, `min`, `max`, `min_by(fn)`, `max_by(fn)`,
`sort(comparator = nil)`, `sort_by(fn)`, `reverse`, `join(sep = "")`,
`contains(v)`, `index_of(v)`, `flatten(depth = nil)`, `uniq`, `zip(other)`,
`enumerate(start = 0)`, `group_by(fn)`, `partition(fn)`, `each_slice(n, fn = nil)`,
`rotate(n = 1)`, `shuffle`, `sample`, `to_map`, `slice(start, length = nil)`.

Mutating: `push`, `append`, `pop`, `shift`, `unshift`, `insert`, `remove`,
`delete`, `delete_at`, `clear`, `rotate`, `shuffle`.

```tapo
[1, 2, 3].map(fn(x) => x * 2)       # [2, 4, 6]
[1, 2, 3, 4].partition(fn(x) => x.even?)
[1, 2, 3].each_slice(2)             # [[1, 2], [3]]
```

Constructors: `List()`, `List("abc")`, `List(range)`.

---

## Map

`size`, `length`, `empty?`, `keys`, `values`, `pairs`, `to_list`,
`get(key, default = nil)`, `fetch(key)`, `set(key, value)`, `has_key?(key)` /
`key?(key)`, `has_value?(value)` / `value?(value)`, `delete(key)`,
`merge(other)`, `merge!(other)` / `update(other)`, `each(fn)`, `each_key(fn)`,
`each_value(fn)`, `map(fn)`, `map_values(fn)`, `filter(fn)` / `select(fn)`,
`reject(fn)`, `invert`, `any?(fn = nil)`, `all?(fn = nil)`, `none?(fn = nil)`.

`map.each(fn)` passes `[key, value]`; `map.map(fn)`/`filter(fn)` pass
`(key, value)`. Dot access reads/writes existing string keys:

```tapo
let m = {a: 1}
m.a          # 1
m.a = 2
m["b"] = 3
```

Constructors: `Map()`, `Map([["a", 1]])`.

---

## Range

`each(fn)`, `to_list`, `map(fn)`, `filter(fn)`, `size`, `length`, `empty?`,
`contains(v)`, `first`, `last`, `min`, `max`, `sum`, `reduce`, `reverse`,
`step(n, fn = nil)`.

```tapo
(1..10).step(3)     # [1, 4, 7, 10]
(3..1).to_list()    # [3, 2, 1]
```

Constructor: `Range(start, end, inclusive = true)`.

---

## Function

`call(...)`, `arity()`, `parameters()`, `name()`.

---

## Generator

A function containing `yield` returns a `Generator`. Generators are lazy and
single-use.

| Method | Meaning |
| --- | --- |
| `next()` | Return the next yielded value; raise `StopIteration` when exhausted. |
| `done?` | True once the generator is exhausted or closed. |
| `each(fn)` | Call `fn` for each remaining value. |
| `to_list()` | Collect all remaining values. |
| `take(n)` | Collect at most `n` values, without over-consuming. |
| `close()` | Close the generator, running its `finally` blocks. |

`for value in generator { ... }` uses the same iteration protocol.

## Bool and Nil

`Bool`: `to_i` (1/0). `Nil` has no special methods beyond the object protocol;
`nil.to_s()` is `"nil"`.

---

## Built-in modules

### `math`

Constants: `PI`, `E`, `TAU`, `INF`, `NAN`.

Functions: `sqrt`, `cbrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`,
`atan2(y, x)`, `log(x, base = e)`, `log2`, `log10`, `exp`, `pow(x, y)`,
`floor`, `ceil`, `hypot`, `degrees`, `radians`, `is_nan`, `is_inf`,
`is_finite`.

### `json`

- `parse(text)` — JSON text to TAPO values.
- `stringify(value, pretty = false)` — TAPO values to JSON text. Instances become
  `{"__class__": "Name", ...fields}`.
- `pretty(value)` — pretty-printed JSON.

### `fs`

`read(path)`, `write(path, text)`, `append(path, text)`, `exists?(path)`,
`is_file?(path)`, `is_dir?(path)`, `list(path)`, `remove(path)`,
`mkdir(path)`, `join(...)`, `basename(path)`, `dirname(path)`,
`extname(path)`, `cwd()`, `size(path)`, `read_lines(path)`,
`write_lines(path, lines)`.

OS errors are reported as TAPO `IOError`.

### `time`

`now()`, `sleep(seconds)`, `format(timestamp, format)`, `iso(timestamp)`.

### `regex`

`match(pattern, text)` returns a map with `match`, `groups`, `captures`,
`start`, `end`, or `nil`. Also `test?(pattern, text)`,
`find_all(pattern, text)`, `replace(pattern, text, replacement)`,
`split(pattern, text)`.

### `random`

`seed(n)`, `random()`, `int(min, max)`, `choice(list)`, `shuffle(list)`,
`sample(list, n)`.

### `encoding`

Base64, Base64URL, hex and URL percent-encoding for UTF-8 strings.

| Function | Meaning |
| --- | --- |
| `encoding.base64_encode(text)` / `base64_decode(text)` | Standard Base64. |
| `encoding.base64url_encode(text)` / `base64url_decode(text)` | URL-safe Base64. |
| `encoding.hex_encode(text)` / `hex_decode(text)` | Hex UTF-8 bytes. |
| `encoding.url_encode(text)` / `url_decode(text)` | `quote_plus`/`unquote_plus`. |

### `hash`

| Function | Meaning |
| --- | --- |
| `hash.md5(text)`, `hash.sha1(text)`, `hash.sha256(text)` | Hex digests. |
| `hash.hmac_sha256(key, text)` | HMAC-SHA256 hex digest. |

### `uuidgen`

Implementation module behind `std/uuid.takg`; import the library for normal use.
It exposes `v4()`, `v5(namespace, name)`, `nil()`, `valid?(text)` and the
`NAMESPACE_*` constants.

### `sys`

`version`, `platform`, `argv`, `pid`, `home`, `env(name, default = nil)`,
`cwd()`, `chdir(path)`, `exit(code = 0)`.

---

## TAPO-level standard library

### `std/test.takg`

`assert_nil`, `assert_not_nil`, `assert_includes`, `assert_excludes`,
`assert_match`, `assert_close`, `refute`, `assert_type`.

```tapo
import "std/test.takg" as T
T.assert_close(0.1 + 0.2, 0.3)
```

### `std/collections.takg`

`chunk(list, n)`, `window(list, n)`, `frequencies(list)`, `group_by(list, fn)`,
`count_by(list, fn)`, `unique_by(list, fn)`, `zip_with(a, b, fn)`,
`flatten(list)`, `intersperse(list, sep)`, `sum_by(list, fn)`,
`max_by(list, fn)`, `min_by(list, fn)`, `range_list(start, stop, step = 1)`,
`partition(list, fn)`.

The same library also provides higher-level helpers: `take_while`, `drop_while`,
`find_map`, `scan`, `chunk_by`, `transpose`, `unzip`, `pairwise`,
`deep_flatten`, `index_by`, `count_if`, `average`, `median`, `mode`, `min_max`,
`zip_longest`, `sort_by_desc`, `pick_keys`, `omit_keys`, `deep_merge`,
`invert_map`, `each_cons`, `chunk_every`, `flat_map`, `sample`, `shuffle`.

### `std/option.takg`

`Option`, `Some(value)`, `None()`. Instances support `some?`, `none?`,
`unwrap`, `unwrap_or(default)`, `map(fn)`, `and_then(fn)`, `or_else(default)`.

### Extra libraries

These optional `.takg` libraries are independent; import each one directly.
`std/functional.takg`, `std/strings.takg`, `std/result.takg`,
`std/validation.takg`, `std/io.takg`, `std/csv.takg`, `std/path.takg` and
`std/cli.takg` are documented in [libraries.md](libraries.md).

| Library | Contents |
| --- | --- |
| `std/functional.takg` | `identity`, `always`, `noop`, `compose`, `pipeline`, `curry2`, `curry3`, `once`, `memoize`, `retry`, `times`, `clamp`, `between?`, `sign`, `sum`, `average`, `tap`, `attempt`. |
| `std/strings.takg` | `words`, `camelize`, `pascalize`, `snake_case`, `kebab_case`, `titleize`, `humanize`, `slugify`, `initials`, `truncate`, `indent`, `dedent`, `wrap`, `escape_html`, `unescape_html`, `pluralize`, `strip_prefix`, `strip_suffix`, `template`, `quote`, `is_blank`. |
| `std/result.takg` | `Result`, `Ok`, `Err`, `ok`, `err`, `try_result`, `collect_results`, `partition_results`, `all_ok?`, `any_ok?`. |
| `std/validation.takg` | `is_email`, `is_url`, `is_uuid`, `is_hex_color`, `is_slug`, `is_numeric`, `is_integer_string`, `is_alpha`, `is_alnum`, `is_ipv4`, `require`, `ensure`, `one_of`, `in_range`, `validate`. |
| `std/io.takg` | `read_text`, `write_text`, `append_text`, `read_json`, `write_json`, `read_jsonl`, `append_jsonl`, `ensure_dir`, `walk`, `copy_text`, `file_size`, `exists?`. |

See [Extra libraries](libraries.md) for examples and details.

---

## Error classes

`Error` is the root; all errors expose `message`, `trace`, `file` and `line`.
Built-ins: `RuntimeError`, `ArgumentError`, `TypeError`, `NameError`,
`AttributeError`, `IndexError`, `KeyError`, `ValueError`, `ZeroDivisionError`,
`AssertionError`, `ImportError`, `IOError`, `MatchError`,
`NotImplementedError`, `FrozenError`, `StopIteration`.

# Extra libraries

TAPO ships with a set of independent `.takg` libraries that are useful in everyday
programs. They are written in TAPO, depend only on the standard library, and can
be imported separately — there is no umbrella package.

```tapo
import "std/strings.takg" as S
import "std/collections.takg" as C

println(S.camelize("hello_world"))   # helloWorld
println(C.median([3, 1, 2]))         # 2
```

| Library | Purpose |
| --- | --- |
| `std/functional.takg` | Function composition, memoisation, retry, small math helpers. |
| `std/strings.takg` | Naming, formatting, wrapping and HTML helpers. |
| `std/collections.takg` | Core collection helpers plus higher-level extras. |
| `std/result.takg` | Explicit `Result` / `Ok` / `Err` values. |
| `std/validation.takg` | Predicates and guard helpers. |
| `std/io.takg` | JSON/JSONL and filesystem conveniences. |

Every library is optional. Import only the ones a file needs.

---

## std/functional.takg

Functional helpers. `compose` runs right-to-left; `pipeline` runs left-to-right.

| Function | Meaning |
| --- | --- |
| `identity(x)` | Return `x`. |
| `always(value)` | Return a zero-argument function that returns `value`. |
| `noop()` | Return `nil`. |
| `compose(...fns)` | `compose(f, g)(x) == f(g(x))`. |
| `pipeline(...fns)` | `pipeline(f, g)(x) == g(f(x))`. |
| `curry2(f)` | `curry2(f)(a)(b) == f(a, b)`. |
| `curry3(f)` | `curry3(f)(a)(b)(c) == f(a, b, c)`. |
| `once(f)` | Call `f` at most once; later calls return the first result. |
| `memoize(f)` | Cache results keyed by `inspect(args)`. |
| `retry(f, attempts = 3)` | Retry on a raised error; returns the first success or raises the last error. |
| `times(n, f)` | List of `f(0) ... f(n - 1)`. |
| `clamp(value, low, high)` | Constrain a number to a range. |
| `between?(value, low, high)` | Inclusive range predicate. |
| `sign(value)` | `-1`, `0` or `1`. |
| `sum(values)` | Add all values, starting at `0`. |
| `average(values)` | Arithmetic mean, or `nil` for an empty list. |
| `tap(value, f)` | Call `f(value)`, then return `value`. |
| `attempt(f)` | `[true, result]` on success, `[false, error]` on failure. |

`memoize` uses structural `inspect`, so lists and maps are valid keys; passing
large or cyclic structures is intentionally not special-cased.

---

## std/strings.takg

Naming and text helpers. Words are split on non-word characters, underscores,
and camel-case boundaries; acronyms such as `HTTP` are preserved as one word.

| Function | Example |
| --- | --- |
| `words(text)` | `words("HelloWorld")` → `["hello", "world"]` |
| `camelize(text)` | `camelize("hello_world")` → `"helloWorld"` |
| `pascalize(text)` | `pascalize("hello_world")` → `"HelloWorld"` |
| `snake_case(text)` | `snake_case("HelloWorld")` → `"hello_world"` |
| `kebab_case(text)` | `kebab_case("HelloWorld")` → `"hello-world"` |
| `titleize(text)` | `titleize("hello_world")` → `"Hello World"` |
| `humanize(text)` | `humanize("hello_world")` → `"Hello world"` |
| `slugify(text)` | `slugify("Hello, World!")` → `"hello-world"` |
| `initials(text)` | `initials("Ada Lovelace")` → `"AL"` |
| `truncate(text, length, ellipsis = "...")` | `truncate("abcdefgh", 5)` → `"ab..."` |
| `indent(text, spaces = 2)` | Indent every line. |
| `dedent(text)` | Remove common leading spaces. |
| `wrap(text, width = 80)` | Soft-wrap on spaces. |
| `escape_html(text)` / `unescape_html(text)` | HTML entity conversion. |
| `pluralize(word, count = 2)` | Simple English pluralization. |
| `strip_prefix(text, prefix)` / `strip_suffix(text, suffix)` | Remove a prefix/suffix when present. |
| `template(text, variables)` | Replace `{{name}}` with `variables["name"].to_s()`. |
| `quote(text)` | Return the inspected, quoted string. |
| `is_blank(text)` | True for empty/whitespace-only text. |
| `split_words(text)` | Alias for `words`. |

`truncate` includes the ellipsis in `length`; if `length` is not larger than the
ellipsis, it returns a plain prefix. `pluralize` is deliberately simple: it
handles `-s`, `-x`, `-z`, `-ch`, `-sh` and consonant + `y`, not irregular nouns.

---

## std/collections.takg

This library contains the core helpers (`chunk`, `window`, `frequencies`,
`group_by`, `count_by`, `unique_by`, `zip_with`, `flatten`, `intersperse`,
`sum_by`, `max_by`, `min_by`, `range_list`, `partition`) and the higher-level
helpers below.

| Function | Meaning |
| --- | --- |
| `take_while(items, f)` | Prefix while `f(item)` is truthy. |
| `drop_while(items, f)` | Drop the prefix while `f(item)` is truthy. |
| `find_map(items, f)` | First non-`nil` result of `f`, else `nil`. |
| `scan(items, initial, f)` | Running fold, including `initial`: `[initial, ...]`. |
| `chunk_by(items, f)` | Consecutive groups as `{"key": key, "items": [...]}`. |
| `transpose(matrix)` | Rows to columns, truncated to the shortest row. |
| `unzip(pairs)` | `[[a, b], ...]` → `[[a...], [b...]]`. |
| `pairwise(items)` | Overlapping two-element windows. |
| `deep_flatten(items)` | Recursively flatten nested lists. |
| `index_by(items, f)` | Map from `f(item)` to item; later duplicates win. |
| `count_if(items, f)` | Count truthy predicate results. |
| `average(items)` / `median(items)` / `mode(items)` | Numeric summaries; empty → `nil`. |
| `min_max(items)` | `[min, max]`, or `[nil, nil]` when empty. |
| `zip_longest(left, right)` | Zip to the longer list, filling with `nil`. |
| `sort_by_desc(items, f)` | Sort by key, descending. |
| `pick_keys(map, keys)` / `omit_keys(map, keys)` | Select or drop map entries. |
| `deep_merge(left, right)` | Recursive map merge; `right` wins. |
| `invert_map(map)` | Swap keys and values. |
| `each_cons(items, n)` / `chunk_every(items, n)` | Aliases for `window` / `chunk`. |
| `flat_map(items, f)` | Alias for the list method. |
| `sample(items, n = 1)` / `shuffle(items)` | Random selection / shuffled copy. |

Callbacks follow the core list conventions: list callbacks receive the element;
map helpers receive `(key, value)`. `median` returns a float for an even number
of elements. `mode` returns the first most frequent value encountered.

---

## std/result.takg

An explicit success/failure type, useful for code that prefers values over
exceptions.

```tapo
import "std/result.takg" as R
import "std/validation.takg" as V

fn parse_age(text) {
  if V.is_integer_string(text) {
    R.ok(Int(text))
  } else {
    R.err(ValueError("not an integer"))
  }
}

let age = parse_age("42").unwrap_or(0)
```

| API | Meaning |
| --- | --- |
| `ok(value)` / `err(error)` | Construct `Ok` / `Err`. |
| `Result.ok?` / `Result.err?` | Status predicates (auto-called as properties). |
| `unwrap(message?)` | Return the value or raise the stored error. |
| `unwrap_err(message?)` | Return the error or raise `ValueError`. |
| `unwrap_or(default)` / `unwrap_or_else(f)` | Value or fallback. |
| `map(f)` / `map_err(f)` | Transform the value or the error. |
| `and_then(f)` / `or_else(f)` | Chain fallible operations. |
| `to_s()` | `Ok(...)` / `Err(...)`. |
| `try_result(f)` | Run `f`, converting a raised error into `Err`. |
| `collect_results(results)` | First `Err`, or `Ok(list_of_values)`. |
| `partition_results(results)` | `[values, errors]`. |
| `all_ok?(results)` / `any_ok?(results)` | Aggregate predicates. |
| `from_option(option, message?)` | Convert `Some`/`None` to `Ok`/`Err`. |

`Result` itself is a normal TAPO class, so subclasses and pattern matching work.

---

## std/validation.takg

Predicates return booleans; guards raise. Regexes are intentionally
approximate and operate on the whole string.

| Function | Checks |
| --- | --- |
| `is_email(text)` | Common `local@domain.tld` shape. |
| `is_url(text)` | `http://` or `https://` followed by non-space text. |
| `is_uuid(text)` | Canonical 8-4-4-4-12 hexadecimal UUID. |
| `is_hex_color(text)` | `#rgb` or `#rrggbb`, `#` optional. |
| `is_slug(text)` | Lowercase alphanumeric words joined by `-`. |
| `is_numeric(text)` | Integer or decimal string, optional sign. |
| `is_integer_string(text)` | Optional sign plus digits. |
| `is_alpha(text)` / `is_alnum(text)` | Unicode letters / letters+digits. |
| `is_ipv4(text)` | Four decimal octets, each 0–255. |
| `require(condition, message?)` | Raise `ArgumentError` if false. |
| `ensure(value, predicate, message?)` | Raise `ValueError` if `predicate(value)` is false; returns `value`. |
| `one_of(value, options, message?)` | Require membership. |
| `in_range(value, low, high, inclusive = true)` | Numeric range check. |
| `validate(value, checks)` | Run a list of `{"test": fn, "message": "..."}` maps. |

```tapo
import "std/validation.takg" as V

V.validate(age, [
  {"test": fn(x) => x >= 0, "message": "age must be non-negative"},
  {"test": fn(x) => x < 150, "message": "age is unrealistic"},
])
```

---

## std/io.takg

JSON/JSONL and filesystem conveniences built on the `json` and `fs` modules.
Errors from the filesystem surface as TAPO `IOError`.

| Function | Meaning |
| --- | --- |
| `read_text(path)` / `write_text(path, text)` | UTF-8 text. |
| `append_text(path, text)` | Append UTF-8 text. |
| `read_json(path)` / `write_json(path, value, pretty = true)` | JSON round-trip. |
| `read_jsonl(path)` | Parse one JSON value per non-blank line. |
| `append_jsonl(path, value)` | Append one JSON value and a newline. |
| `ensure_dir(path)` | Create a directory tree if missing; returns `path`. |
| `walk(dir)` | Recursive list of paths, directories included. |
| `copy_text(source, target)` | Copy UTF-8 text. |
| `file_size(path)` / `exists?(path)` | Filesystem queries. |

`write_json` and `append_jsonl` return the value they wrote. `walk` returns
paths in directory order and does not follow symlinked directories specially.

---

## Notes and limitations

- These libraries are written in TAPO; `fn` is a keyword, so callback parameters are named `f`
  (or another identifier), never `fn`.
- Splat calls use three dots: `f(...args)`, not `f(*args)`.
- TAPO has no `?:` ternary; use `if`/`else` expressions.
- An `else` must appear on the same line as the closing brace: `} else {`.
- Only `nil` and `false` are falsey; `0`, `""` and `[]` are truthy.
- `\w` in TAPO regexes includes `_`, so string splitting uses
  `[^\w]+|_+` to treat underscores as separators.
- Random helpers use the `random` module; call `random.seed(n)` for
  reproducible sequences.

## Tests

The extra libraries are covered by `tests/extras_test.tapo` (test programs remain
`.tapo`):

```bash
./tapo test tests/extras_test.tapo
```

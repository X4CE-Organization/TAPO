"""Command line interface for TAPO.

Usage:
    tapo file.tapo [args...]     run a program
    tapo run file.tapo           run a program
    tapo repl                  interactive session
    tapo test [paths...]       run *_test.tapo files
    tapo fmt [paths...]        format .tapo/.takg sources in place
    tapo new <name>            create a small project scaffold
    tapo audit <paths...>       static security audit
    tapo bench                 run micro-benchmarks
    tapo check <file>          parse without running (.tapo or .takg)
    tapo -e 'code'             evaluate a one-liner
    tapo version               print version information
"""

from __future__ import annotations

import os
import sys

from . import __version__
from .errors import TapoException, TapoExit, TapoSyntaxError
from .interpreter import Interpreter
from .parser import parse
from .formatter import discover as discover_sources, format_file
from .security import SecurityPolicy
from .audit import audit_file
from .bench import run_bench

BANNER = "TAPO %s  \u00b7  \u00a9 2026 X4CE  \u00b7  MIT" % __version__

USAGE = """TAPO \u2014 a small, expressive, object-oriented language

Usage:
  tapo <file.tapo> [args...]   run a program
  tapo run <file.tapo>         run a program
  tapo repl                  start an interactive session
  tapo test [paths...]       run test files (default: tests/)
  tapo fmt [--check] [paths...]  format sources in place (default: .)
  tapo new <name>            create a small project scaffold
  tapo audit [paths...]       static security audit
  tapo bench                 run micro-benchmarks
  tapo check <file>          parse a .tapo program or .takg library
  tapo -e <code>             evaluate code from the command line
  tapo version               show version information
  tapo help                  show this help

Files: programs use .tapo; reusable libraries use .takg.

Security options (before the command/file):
  --sandbox                  deny writes, imports and file reads outside roots
  --allow-read DIR           add a readable directory (repeatable)
  --allow-write DIR          add a writable directory (repeatable)
  --max-steps N              abort after N evaluated nodes
  --max-depth N              abort when call depth exceeds N
  --timeout SECONDS          abort after wall-clock time
  --audit                    print sandbox audit events to stderr

Learn more in docs/manual.md.
"""


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _error_message(value):
    try:
        message = value.fields.get("message")
    except AttributeError:
        message = None
    if message is None:
        message = str(value)
    return str(message)


def print_exception(interp, exc):
    """Print a TAPO runtime error, including its trace, to stderr."""
    value = exc.value
    klass = getattr(value, "klass", None)
    name = getattr(klass, "name", "Error")
    message = _error_message(value)
    file = value.fields.get("file") if hasattr(value, "fields") else None
    line = value.fields.get("line") if hasattr(value, "fields") else None
    sys.stderr.write("\x1b[1;31m%s\x1b[0m: %s\n" % (name, message) if sys.stderr.isatty() else "%s: %s\n" % (name, message))
    if file:
        where = "  at %s" % file
        if line:
            where += ":%s" % line
        sys.stderr.write(where + "\n")
    frames = list(getattr(exc, "trace", []) or [])
    for frame in frames:
        if isinstance(frame, tuple) and len(frame) == 3:
            fn, filename, lineno = frame
            sys.stderr.write("  from %s (%s:%s)\n" % (fn, filename, lineno))
        else:
            sys.stderr.write("  %s\n" % (frame,))


def print_syntax_error(exc, color=False):
    sys.stderr.write(exc.render(color=color and sys.stderr.isatty()) + "\n")


def _add_value_option(policy, name, value):
    if name == "--max-steps":
        try:
            policy.max_steps = int(value)
        except ValueError:
            return "max-steps must be an integer"
    elif name == "--max-depth":
        try:
            policy.max_depth = int(value)
        except ValueError:
            return "max-depth must be an integer"
    elif name == "--timeout":
        try:
            policy.timeout = float(value)
        except ValueError:
            return "timeout must be a number"
    elif name == "--allow-read":
        policy.add_read_root(value)
    elif name == "--allow-write":
        policy.add_write_root(value)
    return None


def parse_global_options(argv):
    """Consume leading security options, returning (policy, remaining, error)."""
    policy = SecurityPolicy()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            i += 1
            break
        if arg in ("--sandbox", "--safe"):
            policy.sandbox = True
            i += 1
            continue
        if arg == "--audit":
            policy.audit = True
            i += 1
            continue
        key, sep, value = arg.partition("=")
        if key in ("--max-steps", "--max-depth", "--timeout", "--allow-read", "--allow-write"):
            if not sep:
                if i + 1 >= len(argv):
                    return policy.refresh(), argv[i:], "%s needs a value" % key
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            error = _add_value_option(policy, key, value)
            if error:
                return policy.refresh(), argv[i:], error
            continue
        if arg.startswith("-"):
            break
        break
    return policy.refresh(), argv[i:], None


def _prepare_policy(policy, interp, script_path=None):
    if policy.sandbox:
        policy.add_read_root(os.getcwd())
        try:
            policy.add_read_root(interp.std_dir())
        except Exception:
            pass
        if script_path:
            policy.add_read_root(os.path.dirname(os.path.abspath(script_path)))
    policy.refresh()
    return policy


def _report_audit(policy):
    if not policy.audit:
        return
    for line in policy.audit_lines():
        sys.stderr.write("audit: %s\n" % line)


def cmd_run(path, args, interp=None, policy=None):
    if not os.path.exists(path):
        sys.stderr.write("tapo: file not found: %s\n" % path)
        return 2
    interp = interp or Interpreter(argv=args)
    policy = policy or SecurityPolicy()
    interp.security = _prepare_policy(policy, interp, path)
    try:
        source = _read(path)
        interp.run_source(source, path)
    except TapoSyntaxError as exc:
        print_syntax_error(exc, color=True)
        return 1
    except TapoException as exc:
        print_exception(interp, exc)
        return 1
    except TapoExit as exc:
        return exc.code
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    finally:
        _report_audit(interp.security)
    return 0


def cmd_eval(code, args, policy=None):
    interp = Interpreter(argv=args)
    interp.security = _prepare_policy(policy or SecurityPolicy(), interp)
    try:
        value, _ = interp.run_source(code, "<command>")
    except TapoSyntaxError as exc:
        print_syntax_error(exc, color=True)
        return 1
    except TapoException as exc:
        print_exception(interp, exc)
        return 1
    except TapoExit as exc:
        return exc.code
    finally:
        _report_audit(interp.security)
    if value is not None:
        print(interp.inspect(value))
    return 0


def cmd_audit(argv):
    paths = argv or ["."]
    files = list(discover_sources(paths, extensions=(".tapo", ".takg")))
    if not files:
        sys.stderr.write("tapo: no sources found\n")
        return 2
    total = 0
    for path in files:
        try:
            findings = audit_file(path)
        except TapoSyntaxError as exc:
            print_syntax_error(exc, color=True)
            total += 1
            continue
        except OSError as exc:
            sys.stderr.write("tapo: cannot audit %s: %s\n" % (path, exc))
            total += 1
            continue
        for severity, line, message in findings:
            print("%s:%s: %s: %s" % (path, line, severity, message))
            total += 1
    if total:
        print("%d finding(s)" % total)
        return 1
    print("no security findings")
    return 0


def cmd_bench(argv):
    return run_bench()


def cmd_new(argv):
    if not argv:
        sys.stderr.write("tapo: new needs a project name\n")
        return 2
    if len(argv) > 1:
        sys.stderr.write("tapo: new takes exactly one project name\n")
        return 2
    name = argv[0]
    target = os.path.abspath(name)
    if os.path.exists(target):
        sys.stderr.write("tapo: target already exists: %s\n" % target)
        return 2
    base = os.path.basename(target.rstrip(os.sep)) or "app"
    try:
        os.makedirs(os.path.join(target, "src"))
        os.makedirs(os.path.join(target, "tests"))
        with open(os.path.join(target, "src", "main.tapo"), "w", encoding="utf-8") as handle:
            handle.write('println("Hello from %s!")\n' % base)
        with open(os.path.join(target, "tests", "main_test.tapo"), "w", encoding="utf-8") as handle:
            handle.write('test("%s starts", fn() {\n  assert_eq(1 + 1, 2)\n})\n' % base)
        with open(os.path.join(target, "README.md"), "w", encoding="utf-8") as handle:
            handle.write(
                "# %s\n\nA TAPO project.\n\n"
                "```bash\ntapo src/main.tapo\ntapo test tests\n```\n" % base
            )
        with open(os.path.join(target, ".gitignore"), "w", encoding="utf-8") as handle:
            handle.write("__pycache__/\n*.py[cod]\ndist/\nbuild/\n")
    except OSError as exc:
        sys.stderr.write("tapo: cannot create project: %s\n" % exc)
        return 2
    print("created %s" % target)
    print("  tapo %s/src/main.tapo" % base)
    print("  tapo test %s/tests" % base)
    return 0


def cmd_fmt(argv):
    check_only = False
    if argv and argv[0] in ("--check", "-c"):
        check_only = True
        argv = argv[1:]
    paths = argv or ["."]
    changed = 0
    total = 0
    for path in discover_sources(paths):
        total += 1
        try:
            did_change, _ = format_file(path, check=check_only)
        except OSError as exc:
            sys.stderr.write("tapo: cannot format %s: %s\n" % (path, exc))
            return 2
        if did_change:
            changed += 1
            if check_only:
                sys.stdout.write("would format %s\n" % path)
            else:
                sys.stdout.write("formatted %s\n" % path)
    if check_only:
        sys.stdout.write("%d file(s) checked, %d need formatting\n" % (total, changed))
        return 1 if changed else 0
    sys.stdout.write("%d file(s) formatted, %d changed\n" % (total, changed))
    return 0


def cmd_check(path):
    if not os.path.exists(path):
        sys.stderr.write("tapo: file not found: %s\n" % path)
        return 2
    try:
        source = _read(path)
        parse(source, path)
    except TapoSyntaxError as exc:
        print_syntax_error(exc, color=True)
        return 1
    print("%s: ok" % path)
    return 0


def _discover_tests(paths):
    if not paths:
        paths = ["tests"]
    found = []
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for name in sorted(files):
                    if name.endswith("_test.tapo"):
                        found.append(os.path.join(root, name))
        elif os.path.isfile(path):
            found.append(path)
        else:
            sys.stderr.write("tapo: test path not found: %s\n" % path)
    return found


def cmd_test(paths):
    files = _discover_tests(paths)
    if not files:
        sys.stderr.write("tapo: no test files found\n")
        return 1
    total = failed = errored = 0
    for path in files:
        interp = Interpreter(argv=[], test_mode=True)
        try:
            source = _read(path)
            interp.run_source(source, path)
        except TapoSyntaxError as exc:
            print_syntax_error(exc, color=True)
            errored += 1
            continue
        except TapoException as exc:
            sys.stderr.write("\n%s\n" % path)
            print_exception(interp, exc)
            errored += 1
            continue
        except TapoExit as exc:
            if exc.code not in (0, None):
                errored += 1
            continue
        if not interp.test_results:
            sys.stderr.write("tapo: warning: %s defines no tests\n" % path)
            continue
        for result in interp.test_results:
            total += 1
            if result.get("ok"):
                sys.stdout.write("  \x1b[32mPASS\x1b[0m %s\n" % result.get("name") if sys.stdout.isatty() else "  PASS %s\n" % result.get("name"))
            else:
                failed += 1
                sys.stdout.write("  \x1b[31mFAIL\x1b[0m %s\n" % result.get("name") if sys.stdout.isatty() else "  FAIL %s\n" % result.get("name"))
                err = result.get("error")
                if err is not None:
                    message = _error_message(err) if hasattr(err, "fields") else str(err)
                    klass = getattr(getattr(err, "klass", None), "name", "Error")
                    sys.stdout.write("       %s: %s\n" % (klass, message))
                    trace = err.fields.get("trace", []) if hasattr(err, "fields") else []
                    for entry in trace:
                        sys.stdout.write("       %s\n" % entry)
    sys.stdout.write("\n%d test(s), %d passed, %d failed, %d file error(s)\n" % (
        total, total - failed, failed, errored))
    return 0 if failed == 0 and errored == 0 else 1


class Repl:
    def __init__(self, argv=None):
        self.interp = Interpreter(argv=argv or [], test_mode=False)
        self.env = self.interp.globals.child() if hasattr(self.interp.globals, "child") else None

    def evaluate(self, source):
        # A fresh child keeps declarations between entries while preventing a
        # syntax error from poisoning the session.
        from .environment import Env
        if self.env is None:
            self.env = Env(self.interp.globals)
        try:
            value, _ = self.interp.run_source(source, "<repl>", env=self.env)
        except TapoSyntaxError as exc:
            print_syntax_error(exc, color=True)
            return
        except TapoException as exc:
            print_exception(self.interp, exc)
            return
        except TapoExit as exc:
            raise SystemExit(exc.code)
        if value is not None:
            try:
                print(self.interp.inspect(value))
            except Exception:
                print(self.interp.to_s(value))

    def run(self):
        print(BANNER)
        print("Type :help for help, :quit to exit.")
        buffer = []
        depth = 0
        while True:
            prompt = "tapo> " if not buffer else "... "
            try:
                line = input(prompt)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print("\n(interrupted)")
                buffer = []
                depth = 0
                continue
            stripped = line.strip()
            if not buffer:
                if stripped in (":quit", ":exit", ":q"):
                    break
                if stripped == ":help":
                    print("  :help   show this help\n  :quit   leave the repl\n  :vars   list global names")
                    continue
                if stripped == ":vars":
                    print(" ".join(sorted(self.interp.globals.names())))
                    continue
            buffer.append(line)
            depth += _bracket_delta(line)
            if depth <= 0 and not line.rstrip().endswith("\\"):
                source = "\n".join(buffer)
                buffer = []
                depth = 0
                if source.strip():
                    self.evaluate(source)


def _bracket_delta(line):
    """Very small bracket counter that ignores strings and comments."""
    depth = 0
    i = 0
    quote = None
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#":
            break
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        i += 1
    return depth


def cmd_repl(argv):
    Repl(argv).run()
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    policy, argv, option_error = parse_global_options(argv)
    if option_error:
        sys.stderr.write("tapo: %s\n" % option_error)
        return 2
    if not argv:
        if sys.stdin.isatty():
            return cmd_repl([])
        sys.stdout.write(USAGE)
        return 0
    first = argv[0]
    if first in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0
    if first in ("-v", "--version", "version"):
        print(BANNER)
        return 0
    if first == "repl":
        return cmd_repl(argv[1:])
    if first == "run":
        extra, rest, error = parse_global_options(argv[1:])
        if error:
            sys.stderr.write("tapo: %s\n" % error)
            return 2
        if extra.active or extra.sandbox or extra.audit:
            policy = extra
        if not rest:
            sys.stderr.write("tapo: run needs a file\n")
            return 2
        return cmd_run(rest[0], rest[1:], policy=policy)
    if first == "test":
        return cmd_test(argv[1:])
    if first == "fmt":
        return cmd_fmt(argv[1:])
    if first == "new":
        return cmd_new(argv[1:])
    if first == "audit":
        return cmd_audit(argv[1:])
    if first == "bench":
        return cmd_bench(argv[1:])
    if first == "check":
        if len(argv) < 2:
            sys.stderr.write("tapo: check needs a file\n")
            return 2
        return cmd_check(argv[1])
    if first in ("-e", "--eval"):
        if len(argv) < 2:
            sys.stderr.write("tapo: -e needs code\n")
            return 2
        return cmd_eval(argv[1], argv[2:], policy)
    if first.startswith("-"):
        sys.stderr.write("tapo: unknown option %s\n" % first)
        return 2
    return cmd_run(first, argv[1:], policy=policy)


if __name__ == "__main__":
    raise SystemExit(main())

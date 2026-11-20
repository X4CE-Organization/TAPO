"""Command line interface for TAPO.

Usage:
    tapo file.tapo [args...]     run a program
    tapo run file.tapo           run a program
    tapo repl                  interactive session
    tapo test [paths...]       run *_test.tapo files
    tapo fmt [paths...]        format .tapo/.takg sources in place
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

BANNER = "TAPO %s  \u00b7  \u00a9 2026 X4CE  \u00b7  MIT" % __version__

USAGE = """TAPO \u2014 a small, expressive, object-oriented language

Usage:
  tapo <file.tapo> [args...]   run a program
  tapo run <file.tapo>         run a program
  tapo repl                  start an interactive session
  tapo test [paths...]       run test files (default: tests/)
  tapo fmt [--check] [paths...]  format sources in place (default: .)
  tapo check <file>          parse a .tapo program or .takg library
  tapo -e <code>             evaluate code from the command line
  tapo version               show version information
  tapo help                  show this help

Files: programs use .tapo; reusable libraries use .takg.

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


def cmd_run(path, args, interp=None):
    if not os.path.exists(path):
        sys.stderr.write("tapo: file not found: %s\n" % path)
        return 2
    interp = interp or Interpreter(argv=args)
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
        if len(argv) < 2:
            sys.stderr.write("tapo: run needs a file\n")
            return 2
        return cmd_run(argv[1], argv[2:])
    if first == "test":
        return cmd_test(argv[1:])
    if first == "fmt":
        return cmd_fmt(argv[1:])
    if first == "check":
        if len(argv) < 2:
            sys.stderr.write("tapo: check needs a file\n")
            return 2
        return cmd_check(argv[1])
    if first in ("-e", "--eval"):
        if len(argv) < 2:
            sys.stderr.write("tapo: -e needs code\n")
            return 2
        interp = Interpreter(argv=argv[2:])
        try:
            value, _ = interp.run_source(argv[1], "<command>")
        except TapoSyntaxError as exc:
            print_syntax_error(exc, color=True)
            return 1
        except TapoException as exc:
            print_exception(interp, exc)
            return 1
        except TapoExit as exc:
            return exc.code
        if value is not None:
            print(interp.inspect(value))
        return 0
    if first.startswith("-"):
        sys.stderr.write("tapo: unknown option %s\n" % first)
        return 2
    return cmd_run(first, argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

"""Python-level tests for sandbox limits, capabilities and static audit."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tapo.audit import audit_source
from tapo.errors import TapoException
from tapo.interpreter import Interpreter
from tapo.security import SecurityPolicy


def run(source, policy):
    interp = Interpreter()
    interp.security = policy
    return interp.run_source(source, "<security-test>")


def expect_security_error(source, policy):
    try:
        run(source, policy)
    except TapoException as exc:
        name = getattr(getattr(exc.value, "klass", None), "name", "")
        assert name == "SecurityError", name
        return
    raise AssertionError("expected SecurityError")


def test_step_limit():
    expect_security_error("var i = 0\nwhile i < 1000 { i += 1 }\n", SecurityPolicy(max_steps=20))


def test_depth_limit():
    source = "fn f(n) { if n == 0 { 0 } else { f(n - 1) } }\nf(50)\n"
    expect_security_error(source, SecurityPolicy(max_depth=5))


def test_sandbox_read_and_write():
    with tempfile.TemporaryDirectory() as root:
        allowed = os.path.join(root, "allowed.txt")
        with open(allowed, "w", encoding="utf-8") as handle:
            handle.write("ok")
        policy = SecurityPolicy(sandbox=True, read_roots=[root])
        value, _ = run('fs.read("%s")' % allowed, policy)
        assert value == "ok"

        expect_security_error('fs.read("/etc/passwd")', SecurityPolicy(sandbox=True, read_roots=[root]))
        expect_security_error('fs.write("%s", "x")' % os.path.join(root, "new.txt"), policy)

        write_policy = SecurityPolicy(sandbox=True, read_roots=[root])
        write_policy.add_write_root(root)
        target = os.path.join(root, "new.txt")
        run('fs.write("%s", "x")' % target, write_policy)
        assert open(target, encoding="utf-8").read() == "x"


def test_sandbox_denies_input_and_env():
    expect_security_error('input("?")', SecurityPolicy(sandbox=True))
    expect_security_error('sys.env("HOME")', SecurityPolicy(sandbox=True))


def test_audit_finds_dangerous_calls():
    source = 'fs.write("x", "y")\ninput("?")\nwhile true { break }\n'
    findings = audit_source(source, "sample.tapo")
    messages = [item[2] for item in findings]
    assert any("fs.write" in message for message in messages), messages
    assert any("input" in message for message in messages), messages
    assert any("while true" in message for message in messages), messages


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("security tests passed")

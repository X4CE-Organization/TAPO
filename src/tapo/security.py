"""Capability policy for running untrusted TAPO programs.

The default policy is unrestricted, preserving TAPO's normal behaviour.  A
sandbox policy restricts reads/writes to explicitly allowed directory trees and
adds step, time and call-depth limits.  All denials are reported as TAPO
``SecurityError`` values with source locations.
"""

from __future__ import annotations

import os
import time


class SecurityPolicy:
    def __init__(
        self,
        sandbox=False,
        max_steps=0,
        max_depth=0,
        timeout=0.0,
        audit=False,
        read_roots=None,
        write_roots=None,
    ):
        self.sandbox = bool(sandbox)
        self.max_steps = int(max_steps or 0)
        self.max_depth = int(max_depth or 0)
        self.timeout = float(timeout or 0.0)
        self.audit = bool(audit)
        self.read_roots = []
        self.write_roots = []
        self.steps = 0
        self.depth = 0
        self.start = time.monotonic()
        self.events = []
        for root in read_roots or []:
            self.add_read_root(root)
        for root in write_roots or []:
            self.add_write_root(root)
        self.active = bool(self.sandbox or self.max_steps or self.max_depth or self.timeout)

    # ------------------------------------------------------------------
    # configuration
    # ------------------------------------------------------------------
    def add_read_root(self, path):
        if path:
            real = os.path.realpath(os.path.abspath(path))
            if real not in self.read_roots:
                self.read_roots.append(real)

    def add_write_root(self, path):
        if path:
            real = os.path.realpath(os.path.abspath(path))
            self.add_read_root(real)
            if real not in self.write_roots:
                self.write_roots.append(real)

    def refresh(self):
        self.active = bool(
            self.sandbox or self.max_steps or self.max_depth or self.timeout
        )
        return self

    # ------------------------------------------------------------------
    # resource accounting
    # ------------------------------------------------------------------
    def tick(self, interp, node=None):
        if not self.active:
            return
        self.steps += 1
        if self.max_steps and self.steps > self.max_steps:
            interp.error(
                "SecurityError",
                "step limit exceeded (%d steps)" % self.max_steps,
                node,
            )
        if self.timeout and (time.monotonic() - self.start) > self.timeout:
            interp.error(
                "SecurityError",
                "time limit exceeded (%.2fs)" % self.timeout,
                node,
            )

    def enter_call(self, interp, node=None):
        if not self.active:
            return
        self.depth += 1
        if self.max_depth and self.depth > self.max_depth:
            interp.error(
                "SecurityError",
                "call-depth limit exceeded (%d)" % self.max_depth,
                node,
            )

    def leave_call(self):
        if self.depth > 0:
            self.depth -= 1

    # ------------------------------------------------------------------
    # capabilities
    # ------------------------------------------------------------------
    def _inside(self, real, roots):
        for root in roots:
            if not root:
                continue
            try:
                if os.path.commonpath([real, root]) == root:
                    return True
            except ValueError:
                # Different drives (Windows): no common path.
                continue
        return False

    def check_path(self, interp, path, write=False, node=None):
        if not self.sandbox:
            return path
        real = os.path.realpath(os.path.abspath(path))
        roots = self.write_roots if write else self.read_roots
        if not self._inside(real, roots):
            action = "write" if write else "read"
            interp.error(
                "SecurityError",
                "sandbox denied %s outside allowed roots: %s" % (action, real),
                node,
            )
        self.record("%s" % ("fs.write" if write else "fs.read"), real)
        return real

    def check_import(self, interp, path, node=None):
        if not self.sandbox:
            return path
        real = os.path.realpath(os.path.abspath(path))
        if not self._inside(real, self.read_roots):
            interp.error(
                "SecurityError",
                "sandbox denied import outside allowed roots: %s" % real,
                node,
            )
        self.record("import", real)
        return real

    def deny(self, interp, action, node=None):
        interp.error("SecurityError", "sandbox denied operation: %s" % action, node)

    def record(self, event, detail=""):
        self.events.append((event, detail))

    def audit_lines(self):
        return ["%s: %s" % (event, detail) for event, detail in self.events]

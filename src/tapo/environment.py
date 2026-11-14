"""Lexical environments for the TAPO interpreter."""

from __future__ import annotations


class Env:
    __slots__ = ("parent", "vars", "constants", "exports")

    def __init__(self, parent=None):
        self.parent = parent
        self.vars = {}
        self.constants = set()
        self.exports = set()

    def define(self, name, value, const=False):
        self.vars[name] = value
        if const:
            self.constants.add(name)
        else:
            self.constants.discard(name)

    def define_export(self, name, value, const=False):
        self.define(name, value, const)
        self.exports.add(name)

    def contains_local(self, name):
        return name in self.vars

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise KeyError(name)

    def find_env(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return env
            env = env.parent
        return None

    def set(self, name, value):
        """Assign to the nearest existing binding.

        Returns "ok", "const" or "missing".
        """
        env = self.find_env(name)
        if env is None:
            return "missing"
        if name in env.constants:
            return "const"
        env.vars[name] = value
        return "ok"

    def names(self):
        out = []
        env = self
        while env is not None:
            for name in env.vars:
                if name not in out:
                    out.append(name)
            env = env.parent
        return out

    def local_names(self):
        return list(self.vars.keys())

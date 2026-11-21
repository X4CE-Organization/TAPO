"""The TAPO tree-walking interpreter.

The interpreter evaluates the AST directly.  It favours clarity and good error
messages over raw speed; TAPO is a language for expressing ideas, and the whole
runtime is deliberately small enough to read in an afternoon.
"""

from __future__ import annotations

import difflib
import json
import math
import os
import sys

from . import ast as A
from . import builtins as B
from .environment import Env
from .errors import TapoBreak, TapoContinue, TapoException, TapoExit, TapoReturn
from .security import SecurityPolicy
from .objects import (
    AdviceFn,
    Frame,
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
    make_error_classes,
)

_MISSING = object()

NOARG_GENERIC_PREDICATES = {"nil?"}


def contains_yield(node):
    """True when *node* contains a yield that belongs to this function."""
    if isinstance(node, A.Yield):
        return True
    if isinstance(node, (A.FnDecl, A.Lambda, A.ClassDecl, A.MixinDecl, A.AspectDecl)):
        return False
    if isinstance(node, (list, tuple)):
        return any(contains_yield(item) for item in node)
    if hasattr(node, "__dict__"):
        return any(contains_yield(item) for item in vars(node).values())
    return False


class Interpreter:
    def __init__(self, argv=None, test_mode=False):
        self.globals = Env()
        self.module_cache = {}
        self.loading_modules = []
        self.frames = []
        self.call_stack = []
        self.file_stack = ["<input>"]
        self.test_mode = test_mode
        self.test_results = []
        self.argv = list(argv or [])
        self._inspect_depth = 0
        self._builtin_node = None
        self.security = SecurityPolicy()
        self.class_registry = []

        self.error_classes = make_error_classes()
        self.builtin_classes = {}
        self.class_class = None
        self.function_class = None
        B.install(self, self.globals)

    # ------------------------------------------------------------------
    # top level
    # ------------------------------------------------------------------
    @property
    def current_file(self):
        return self.file_stack[-1] if self.file_stack else "<input>"

    def run_source(self, source, filename="<input>", env=None, is_module=False):
        """Parse and evaluate *source*.  Returns ``(value, env)``."""
        from .parser import parse

        program = parse(source, filename)
        if env is None:
            env = Env(self.globals)
            env.define("__file__", filename, const=True)
            env.define("__name__", "__main__" if not is_module else os.path.basename(filename), const=True)
        self.file_stack.append(filename)
        try:
            try:
                value = self.eval_block(program, env)
            except TapoReturn as ret:
                value = ret.value
        finally:
            self.file_stack.pop()
        return value, env

    def run_file(self, path, env=None):
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        absolute = os.path.abspath(path)
        return self.run_source(source, absolute, env=env)

    # ------------------------------------------------------------------
    # statements and expressions
    # ------------------------------------------------------------------
    def eval_block(self, block, env):
        value = None
        defers = []
        try:
            for stmt in block.stmts:
                if isinstance(stmt, A.Defer):
                    defers.append(stmt)
                else:
                    value = self.eval(stmt, env)
            return value
        finally:
            for deferred in reversed(defers):
                self.eval(deferred.body, env)

    def eval(self, node, env):
        if self.security.active:
            self.security.tick(self, node)
        if isinstance(node, A.Block):
            return self.eval_block(node, env)
        if isinstance(node, A.Literal):
            return node.value
        if isinstance(node, A.Interp):
            out = []
            for part in node.parts:
                if isinstance(part, str):
                    out.append(part)
                else:
                    out.append(self.to_s(self.eval(part, env)))
            return "".join(out)
        if isinstance(node, A.ListLit):
            out = []
            for item in node.items:
                if isinstance(item, A.Splat):
                    out.extend(self.iter_values(self.eval(item.expr, env), node))
                else:
                    out.append(self.eval(item, env))
            return out
        if isinstance(node, A.MapLit):
            out = {}
            for key_node, value_node in node.pairs:
                key = self.eval(key_node, env)
                out[key] = self.eval(value_node, env)
            return out
        if isinstance(node, A.Identifier):
            return self.lookup_name(node.name, env, node)
        if isinstance(node, A.Placeholder):
            try:
                return env.lookup("_")
            except KeyError:
                self.error("ValueError", "'_' is only valid inside a pipeline", node)
        if isinstance(node, A.SelfExpr):
            frame = self.frames[-1] if self.frames else None
            if frame is None or frame.self_obj is None:
                self.error("ValueError", "'self' can only be used inside a method", node)
            return frame.self_obj
        if isinstance(node, A.SuperExpr):
            return self.eval_super(node)
        if isinstance(node, A.Unary):
            return self.unary_op(node.op, self.eval(node.operand, env), node)
        if isinstance(node, A.Binary):
            if node.op == "and":
                left = self.eval(node.left, env)
                return self.eval(node.right, env) if self.truthy(left) else left
            if node.op == "or":
                left = self.eval(node.left, env)
                return left if self.truthy(left) else self.eval(node.right, env)
            if node.op == "??":
                left = self.eval(node.left, env)
                return self.eval(node.right, env) if left is None else left
            left = self.eval(node.left, env)
            right = self.eval(node.right, env)
            return self.binary_op(node.op, left, right, node)
        if isinstance(node, A.Pipe):
            return self.eval_pipe(node, env)
        if isinstance(node, A.Assign):
            return self.eval_assign(node, env)
        if isinstance(node, A.Call):
            if isinstance(node.callee, A.Attr):
                callee = self.eval_attr(node.callee.obj, node.callee.name, node.callee, env, auto_predicate=False)
            elif isinstance(node.callee, A.Identifier):
                callee = self.lookup_name(node.callee.name, env, node.callee, auto_predicate=False)
            else:
                callee = self.eval(node.callee, env)
            args = self.eval_args(node.args, env)
            return self.call_value(callee, args, node)
        if isinstance(node, A.Attr):
            return self.eval_attr(node.obj, node.name, node, env)
        if isinstance(node, A.Index):
            obj = self.eval(node.obj, env)
            index = self.eval(node.index, env)
            return self.get_index(obj, index, node)
        if isinstance(node, A.Splat):
            self.error("ValueError", "a splat is only valid inside a call or list literal", node)
        if isinstance(node, A.Param):
            self.error("ValueError", "unexpected parameter", node)
        if isinstance(node, A.Lambda):
            return self.make_function(node.name, node.params, node.body, env, node)
        if isinstance(node, A.With):
            return self.eval_with(node, env)
        if isinstance(node, A.EnumDecl):
            return self.eval_enum(node, env)
        if isinstance(node, A.Defer):
            self.error("ValueError", "defer is only valid inside a block", node)
        if isinstance(node, A.Yield):
            self.error("ValueError", "yield is only valid inside a function", node)
        if isinstance(node, A.If):
            if self.truthy(self.eval(node.cond, env)):
                return self.eval_block(node.then, Env(env))
            if node.otherwise is not None:
                return self.eval_block(node.otherwise, Env(env))
            return None
        if isinstance(node, A.While):
            while True:
                cond = self.truthy(self.eval(node.cond, env))
                if node.is_until:
                    cond = not cond
                if not cond:
                    break
                try:
                    self.eval_block(node.body, Env(env))
                except TapoContinue:
                    continue
                except TapoBreak:
                    break
            return None
        if isinstance(node, A.For):
            iterable = self.iter_values(self.eval(node.iterable, env), node)
            for item in iterable:
                loop_env = Env(env)
                self.declare_pattern(node.pattern, item, loop_env, const=False, node=node)
                try:
                    self.eval_block(node.body, loop_env)
                except TapoContinue:
                    continue
                except TapoBreak:
                    break
            return None
        if isinstance(node, A.Loop):
            while True:
                try:
                    self.eval_block(node.body, Env(env))
                except TapoContinue:
                    continue
                except TapoBreak:
                    break
            return None
        if isinstance(node, A.Return):
            value = self.eval(node.value, env) if node.value is not None else None
            raise TapoReturn(value)
        if isinstance(node, A.Break):
            raise TapoBreak()
        if isinstance(node, A.Continue):
            raise TapoContinue()
        if isinstance(node, A.Try):
            return self.eval_try(node, env)
        if isinstance(node, A.Raise):
            value = self.eval(node.value, env) if node.value is not None else None
            self.raise_value(value, node)
        if isinstance(node, A.Match):
            return self.eval_match(node, env)
        if isinstance(node, A.VarDecl):
            value = self.eval(node.value, env) if node.value is not None else None
            self.declare_pattern(node.pattern, value, env, const=(node.kind == "let"), node=node)
            return value
        if isinstance(node, A.FnDecl):
            fn = self.make_function(node.name, node.params, node.body, env, node, is_method=False)
            env.define(node.name, fn, const=False)
            return fn
        if isinstance(node, A.ClassDecl):
            return self.eval_class(node, env)
        if isinstance(node, A.MixinDecl):
            return self.eval_mixin(node, env)
        if isinstance(node, A.AspectDecl):
            return self.eval_aspect(node, env)
        if isinstance(node, A.Import):
            return self.eval_import(node, env)
        if isinstance(node, A.Export):
            value = self.eval(node.decl, env)
            for name in self.declared_names(node.decl):
                env.exports.add(name)
            return value
        if isinstance(node, (A.GetterDecl, A.SetterDecl)):
            self.error("ValueError", "get/set declarations are only valid inside a class or mixin", node)
        if isinstance(node, A.UseAspect):
            self.error("ValueError", "'use' is only valid inside a class body", node)
        if isinstance(node, A.MatchArm):
            self.error("ValueError", "unexpected match arm", node)
        self.error("ValueError", "cannot evaluate %s" % type(node).__name__, node)

    def eval_args(self, arg_nodes, env):
        args = []
        for arg in arg_nodes:
            if isinstance(arg, A.Splat):
                args.extend(self.iter_values(self.eval(arg.expr, env), arg))
            else:
                args.append(self.eval(arg, env))
        return args

    def eval_attr(self, obj_node, name, node, env, auto_predicate=True):
        obj = self.eval(obj_node, env)
        if node.safe and obj is None:
            return None
        return self.get_attr(obj, name, node, auto_predicate=auto_predicate)

    def eval_pipe(self, node, env):
        left = self.eval(node.left, env)
        if node.has_placeholder:
            pipe_env = Env(env)
            pipe_env.define("_", left, const=True)
            return self.eval(node.right, pipe_env)
        right = node.right
        if isinstance(right, A.Call):
            if isinstance(right.callee, A.Attr):
                callee = self.eval_attr(
                    right.callee.obj, right.callee.name, right.callee, env, auto_predicate=False
                )
            else:
                callee = self.eval(right.callee, env)
            args = [left] + self.eval_args(right.args, env)
            return self.call_value(callee, args, node)
        if isinstance(right, A.Attr):
            callee = self.eval_attr(right.obj, right.name, right, env, auto_predicate=False)
            return self.call_value(callee, [left], node)
        callee = self.eval(right, env)
        return self.call_value(callee, [left], node)

    def eval_super(self, node):
        frame = self.frames[-1] if self.frames else None
        if frame is None or frame.defining_class is None:
            self.error("ValueError", "'super' can only be used inside a method", node)
        defining = frame.defining_class
        if defining.superclass is None:
            self.error("AttributeError", "%s has no superclass" % defining.name, node)
        method_name = node.method or frame.method_name
        if method_name is None:
            self.error("ValueError", "'super' needs a method name here", node)
        owner = defining.superclass
        found_owner, fn = owner.find_method(method_name)
        if fn is None:
            self.error(
                "AttributeError",
                "no superclass method '%s' found for %s" % (method_name, defining.name),
                node,
            )
        return TapoBoundMethod(frame.self_obj, method_name, fn, found_owner, allow_aspects=False)

    def eval_assign(self, node, env):
        target = node.target
        if isinstance(target, A.Identifier):
            if node.op == "=":
                value = self.eval(node.value, env)
                return self.store_name(target.name, value, env, node)
            current = self.lookup_name(target.name, env, node)
            if node.op == "??=":
                if current is not None:
                    return current
                value = self.eval(node.value, env)
                return self.store_name(target.name, value, env, node)
            value = self.eval(node.value, env)
            result = self.binary_op(node.op[:-1], current, value, node)
            return self.store_name(target.name, result, env, node)
        if isinstance(target, A.Attr):
            obj = self.eval(target.obj, env)
            if node.op == "=":
                value = self.eval(node.value, env)
                self.set_attr(obj, target.name, value, node)
                return value
            current = self.get_attr(obj, target.name, target)
            if node.op == "??=":
                if current is not None:
                    return current
                value = self.eval(node.value, env)
                self.set_attr(obj, target.name, value, node)
                return value
            value = self.eval(node.value, env)
            result = self.binary_op(node.op[:-1], current, value, node)
            self.set_attr(obj, target.name, result, node)
            return result
        if isinstance(target, A.Index):
            obj = self.eval(target.obj, env)
            index = self.eval(target.index, env)
            if node.op == "=":
                value = self.eval(node.value, env)
                self.set_index(obj, index, value, node)
                return value
            current = self.get_index(obj, index, node)
            if node.op == "??=":
                if current is not None:
                    return current
                value = self.eval(node.value, env)
                self.set_index(obj, index, value, node)
                return value
            value = self.eval(node.value, env)
            result = self.binary_op(node.op[:-1], current, value, node)
            self.set_index(obj, index, result, node)
            return result
        self.error("ValueError", "invalid assignment target", node)

    def store_name(self, name, value, env, node):
        status = env.set(name, value)
        if status == "const":
            self.error("FrozenError", "cannot assign to constant '%s'" % name, node)
        if status == "missing":
            self.error("NameError", "undefined variable '%s'" % name, node)
        return value

    def eval_try(self, node, env):
        result = None
        try:
            try:
                result = self.eval_block(node.body, Env(env))
            except TapoException as exc:
                if node.catch_body is None:
                    raise
                catch_env = Env(env)
                if node.catch_name:
                    catch_env.define(node.catch_name, exc.value, const=False)
                result = self.eval_block(node.catch_body, catch_env)
        finally:
            if node.finally_body is not None:
                self.eval_block(node.finally_body, Env(env))
        return result

    def eval_match(self, node, env):
        subject = self.eval(node.subject, env)
        for arm in node.arms:
            arm_env = Env(env)
            bindings = self.match_pattern(arm.pattern, subject, env)
            if bindings is None:
                continue
            for name, value in bindings.items():
                arm_env.define(name, value, const=False)
            if arm.guard is not None and not self.truthy(self.eval(arm.guard, arm_env)):
                continue
            return self.eval_block(arm.body, arm_env)
        self.error(
            "MatchError",
            "no pattern matched value %s" % self.inspect(subject),
            node,
        )

    # ------------------------------------------------------------------
    # generators (yield)
    # ------------------------------------------------------------------
    def _generator_run(self, fn, args, node=None, self_obj=None,
                       defining_class=None, method_name=None, display_name=None):
        """Drive one generator function, suspending at every yield."""
        if self_obj is None:
            self_obj = fn.lexical_self
        if defining_class is None:
            defining_class = fn.defining_class
        call_env = Env(fn.closure)
        if self_obj is not None:
            call_env.define("self", self_obj, const=True)
        self.bind_params(fn, args, call_env, node)
        frame = Frame(self_obj, defining_class, method_name or fn.name)
        info = (display_name or fn.name, self.current_file, node.line if node is not None else 0)
        filename = fn.filename
        self.security.enter_call(self, node)
        self.frames.append(frame)
        self.call_stack.append(info)
        if filename:
            self.file_stack.append(filename)

        def suspend(value):
            # The generator's frame must not be visible to code that runs
            # between two yields.  Put it back when the generator resumes.
            self.frames.pop()
            self.call_stack.pop()
            file_popped = False
            if filename and self.file_stack and self.file_stack[-1] == filename:
                self.file_stack.pop()
                file_popped = True
            try:
                yield value
            finally:
                self.frames.append(frame)
                self.call_stack.append(info)
                if file_popped:
                    self.file_stack.append(filename)

        try:
            try:
                result = yield from self.gen_eval(fn.body, call_env, suspend)
                return result
            except TapoReturn as ret:
                return ret.value
        except TapoException as exc:
            self.add_note(exc, info[0], node)
            raise
        finally:
            if frame in self.frames:
                self.frames.remove(frame)
            if filename:
                for i in range(len(self.file_stack) - 1, -1, -1):
                    if self.file_stack[i] == filename:
                        del self.file_stack[i]
                        break
            if info in self.call_stack:
                for i in range(len(self.call_stack) - 1, -1, -1):
                    if self.call_stack[i] is info:
                        del self.call_stack[i]
                        break
            self.security.leave_call()

    def gen_eval(self, node, env, suspend):
        """Evaluate a node with yield support, delegating ordinary nodes."""
        if isinstance(node, A.Block):
            result = None
            defers = []
            try:
                for stmt in node.stmts:
                    if isinstance(stmt, A.Defer):
                        defers.append(stmt)
                    else:
                        result = yield from self.gen_eval(stmt, env, suspend)
                return result
            finally:
                for deferred in reversed(defers):
                    yield from self.gen_eval(deferred.body, env, suspend)
        if isinstance(node, A.Yield):
            value = self.eval(node.value, env) if node.value is not None else None
            yield from suspend(value)
            return None
        if isinstance(node, A.If):
            if self.truthy(self.eval(node.cond, env)):
                return (yield from self.gen_eval(node.then, Env(env), suspend))
            if node.otherwise is not None:
                return (yield from self.gen_eval(node.otherwise, Env(env), suspend))
            return None
        if isinstance(node, A.While):
            while True:
                cond = self.truthy(self.eval(node.cond, env))
                if node.is_until:
                    cond = not cond
                if not cond:
                    break
                try:
                    yield from self.gen_eval(node.body, Env(env), suspend)
                except TapoContinue:
                    continue
                except TapoBreak:
                    break
            return None
        if isinstance(node, A.For):
            iterable = self.iter_values(self.eval(node.iterable, env), node)
            for item in iterable:
                loop_env = Env(env)
                self.declare_pattern(node.pattern, item, loop_env, const=False, node=node)
                try:
                    yield from self.gen_eval(node.body, loop_env, suspend)
                except TapoContinue:
                    continue
                except TapoBreak:
                    break
            return None
        if isinstance(node, A.Loop):
            while True:
                try:
                    yield from self.gen_eval(node.body, Env(env), suspend)
                except TapoContinue:
                    continue
                except TapoBreak:
                    break
            return None
        if isinstance(node, A.Try):
            result = None
            try:
                try:
                    result = yield from self.gen_eval(node.body, Env(env), suspend)
                except TapoException as exc:
                    if node.catch_body is None:
                        raise
                    catch_env = Env(env)
                    if node.catch_name:
                        catch_env.define(node.catch_name, exc.value, const=False)
                    result = yield from self.gen_eval(node.catch_body, catch_env, suspend)
            finally:
                if node.finally_body is not None:
                    yield from self.gen_eval(node.finally_body, Env(env), suspend)
            return result
        if isinstance(node, A.With):
            resource = self.eval(node.resource, env)
            body_env = Env(env)
            if node.name is not None:
                body_env.define(node.name, resource, const=True)
            if not self.responds_to(resource, "close"):
                self.error("TypeError", "with resource must respond to close", node)
            try:
                return (yield from self.gen_eval(node.body, body_env, suspend))
            finally:
                self.call_value(self.get_attr(resource, "close", node), [], node)
        if isinstance(node, A.Match):
            subject = self.eval(node.subject, env)
            for arm in node.arms:
                arm_env = Env(env)
                bindings = self.match_pattern(arm.pattern, subject, env)
                if bindings is None:
                    continue
                for name, value in bindings.items():
                    arm_env.define(name, value, const=False)
                if arm.guard is not None and not self.truthy(self.eval(arm.guard, arm_env)):
                    continue
                return (yield from self.gen_eval(arm.body, arm_env, suspend))
            self.error(
                "MatchError",
                "no pattern matched value %s" % self.inspect(subject),
                node,
            )
        return self.eval(node, env)

    # ------------------------------------------------------------------
    # functions, methods and constructors
    # ------------------------------------------------------------------
    def make_function(self, name, params, body, env, node, is_method=False, defining_class=None):
        frame = self.frames[-1] if self.frames else None
        if defining_class is None and frame is not None:
            defining_class = frame.defining_class
        lexical_self = frame.self_obj if frame is not None else None
        return TapoFunction(
            name,
            params,
            body,
            env,
            filename=self.current_file,
            defining_class=defining_class,
            lexical_self=lexical_self,
            is_method=is_method,
            line=node.line if node is not None else 0,
            is_generator=contains_yield(body),
        )

    def call_value(self, callee, args, node=None):
        if isinstance(callee, TapoFunction):
            return self.call_function(callee, args, node=node)
        if isinstance(callee, TapoBoundMethod):
            return self.invoke_bound(callee, args, node)
        if isinstance(callee, TapoBuiltin):
            previous = self._builtin_node
            self._builtin_node = node
            try:
                try:
                    return callee.fn(self, args)
                except TapoException as exc:
                    self.add_note(exc, callee.name, node)
                    raise
            finally:
                self._builtin_node = previous
        if isinstance(callee, TapoBoundBuiltin):
            previous = self._builtin_node
            self._builtin_node = node
            try:
                try:
                    return callee.fn(self, callee.receiver, args)
                except TapoException as exc:
                    self.add_note(exc, callee.name, node)
                    raise
            finally:
                self._builtin_node = previous
        if isinstance(callee, TapoClass):
            return self.instantiate(callee, args, node)
        if isinstance(callee, TapoProceed):
            if len(args) > 1:
                self.error("ArgumentError", "proceed expects zero or one argument (a new argument list)", node)
            return callee.callback(args[0] if args else None)
        if isinstance(callee, TapoDynamicMethod):
            owner, mm = callee.instance.klass.find_method("method_missing")
            if mm is None:
                self.error("AttributeError", "undefined method '%s'" % callee.name, node)
            bound = TapoBoundMethod(callee.instance, "method_missing", mm, owner, allow_aspects=False)
            return self.invoke_bound(bound, [callee.name, list(args)], node)
        if isinstance(callee, TapoInstance):
            owner, fn = callee.klass.find_method("call")
            if fn is not None:
                bound = TapoBoundMethod(callee, "call", fn, owner, allow_aspects=True)
                return self.invoke_bound(bound, args, node)
        self.error("TypeError", "%s is not callable" % self.inspect(callee), node)

    def call_function(
        self,
        fn,
        args,
        node=None,
        self_obj=None,
        defining_class=None,
        method_name=None,
        display_name=None,
    ):
        if self_obj is None:
            self_obj = fn.lexical_self
        if defining_class is None:
            defining_class = fn.defining_class
        if getattr(fn, "is_generator", False):
            return TapoGenerator(
                self, fn, args, node, self_obj, defining_class,
                method_name, display_name,
            )
        call_env = Env(fn.closure)
        if self_obj is not None:
            call_env.define("self", self_obj, const=True)
        self.bind_params(fn, args, call_env, node)
        frame = Frame(self_obj, defining_class, method_name or fn.name)
        info = (display_name or fn.name, self.current_file, node.line if node is not None else 0)
        old_file = self.current_file
        self.security.enter_call(self, node)
        self.frames.append(frame)
        self.call_stack.append(info)
        if fn.filename:
            self.file_stack.append(fn.filename)
        try:
            try:
                return self.eval_block(fn.body, call_env)
            except TapoReturn as ret:
                return ret.value
        except TapoException as exc:
            self.add_note(exc, info[0], node)
            raise
        finally:
            if fn.filename:
                self.file_stack.pop()
            self.call_stack.pop()
            self.frames.pop()
            self.security.leave_call()

    def bind_params(self, fn, args, call_env, node):
        index = 0
        for param in fn.params:
            if param.is_rest:
                value = args[index:]
                index = len(args)
            elif index < len(args):
                value = args[index]
                index += 1
            elif param.default is not None:
                value = self.eval(param.default, call_env)
            else:
                self.arity_error(fn, args, node)
            bindings = self.match_pattern(param.pattern, value, call_env)
            if bindings is None:
                self.error(
                    "ArgumentError",
                    "argument %s does not match parameter pattern in %s"
                    % (self.inspect(value), fn.name),
                    node,
                )
            for name, bound in bindings.items():
                call_env.define(name, bound, const=False)
        if index < len(args):
            self.arity_error(fn, args, node)

    def arity_error(self, fn, args, node):
        required = len([p for p in fn.params if not p.is_rest and p.default is None])
        total = len(fn.params)
        has_rest = any(p.is_rest for p in fn.params)
        if has_rest:
            expected = "at least %d" % required
        elif required == total:
            expected = "%d" % required
        else:
            expected = "%d..%d" % (required, total)
        self.error(
            "ArgumentError",
            "%s expects %s argument(s), got %d" % (fn.name, expected, len(args)),
            node,
        )

    def invoke_bound(self, bound, args, node=None):
        if bound.allow_aspects and isinstance(bound.instance, TapoInstance):
            aspects = [
                aspect
                for aspect in bound.instance.klass.effective_aspects()
                if aspect.matching(bound.name)
            ]
            if aspects:
                return self.invoke_with_aspects(bound, list(args), aspects, node)
        return self.call_function(
            bound.function,
            args,
            node=node,
            self_obj=bound.instance,
            defining_class=bound.owner,
            method_name=bound.name,
        )

    def invoke_method(self, receiver, name, args, node=None):
        value = self.get_attr(receiver, name, node, auto_predicate=False)
        return self.call_value(value, args, node)

    def invoke_with_aspects(self, bound, args, aspects, node):
        instance = bound.instance

        def layer(index, current_args):
            if index >= len(aspects):
                return self.call_function(
                    bound.function,
                    list(current_args),
                    node=node,
                    self_obj=instance,
                    defining_class=bound.owner,
                    method_name=bound.name,
                )
            aspect = aspects[index]
            advices = aspect.matching(bound.name)
            before = [a for a in advices if a.kind == "before"]
            after = [a for a in advices if a.kind == "after"]
            around = [a for a in advices if a.kind == "around"]
            if len(around) > 1:
                self.error(
                    "RuntimeError",
                    "aspect %s has more than one around advice for method '%s'"
                    % (aspect.name, bound.name),
                    node,
                )
            for advice in before:
                self.call_advice(advice, bound, current_args, None, node)
            if around:
                def proceed_callback(new_args, captured=list(current_args)):
                    if new_args is None:
                        return layer(index + 1, captured)
                    if not isinstance(new_args, list):
                        self.error("TypeError", "proceed expects a list of arguments", node)
                    return layer(index + 1, list(new_args))

                proceed = TapoProceed(self, proceed_callback, "%s.%s" % (aspect.name, bound.name))
                result = self.call_advice(around[0], bound, current_args, proceed, node)
            else:
                result = layer(index + 1, current_args)
            for advice in after:
                # After advice is for side effects; use around to transform.
                self.call_advice(advice, bound, current_args, result, node)
            return result

        return layer(0, list(args))

    def call_advice(self, advice, bound, args, extra, node):
        payload = [bound.instance, bound.name, args]
        if advice.kind == "before":
            payload = payload
        elif advice.kind == "after":
            payload = payload + [extra]
        else:
            payload = payload + [extra]
        label = "%s advice for %s" % (advice.kind, bound.name)
        return self.call_function(
            advice.function,
            payload,
            node=node,
            self_obj=bound.instance,
            display_name=label,
        )

    def instantiate(self, klass, args, node=None):
        if klass.native is not None:
            previous = self._builtin_node
            self._builtin_node = node
            try:
                return klass.native(self, args, node)
            finally:
                self._builtin_node = previous
        instance = TapoInstance(klass)
        self.init_fields(instance)
        owner, init = klass.find_method("init")
        if init is not None:
            bound = TapoBoundMethod(instance, "init", init, owner, allow_aspects=True)
            self.invoke_bound(bound, list(args), node)
            if klass.is_error:
                instance.fields.setdefault("message", self.to_s(args[0]) if args else klass.name)
                instance.fields.setdefault("trace", [])
        elif klass.is_error:
            if len(args) > 1:
                self.error(
                    "ArgumentError",
                    "%s expects at most one argument, got %d" % (klass.name, len(args)),
                    node,
                )
            instance.fields["message"] = self.to_s(args[0]) if args else klass.name
            instance.fields.setdefault("trace", [])
        elif args:
            # Convenience: a class without init() can be constructed from
            # positional field values, in declaration order.
            specs = klass.field_specs()
            if len(args) > len(specs):
                self.error(
                    "ArgumentError",
                    "%s has no init method and only %d field(s), but got %d argument(s)"
                    % (klass.name, len(specs), len(args)),
                    node,
                )
            for (field_name, _default, _env), value in zip(specs, args):
                instance.fields[field_name] = value
        return instance

    def init_fields(self, instance):
        for name, expr, defining_env in instance.klass.field_specs():
            field_env = Env(defining_env)
            field_env.define("self", instance, const=True)
            instance.fields[name] = self.eval(expr, field_env)

    # ------------------------------------------------------------------
    # classes, mixins and aspects
    # ------------------------------------------------------------------
    def make_method(self, name, params, body, env, klass, node, is_method=True):
        return TapoFunction(
            name,
            params,
            body,
            env,
            filename=self.current_file,
            defining_class=klass,
            lexical_self=None,
            is_method=is_method,
            line=node.line if node is not None else 0,
            is_generator=contains_yield(body),
        )

    def eval_class(self, node, env):
        superclass = self.Object if node.superclass is None else self.eval(node.superclass, env)
        if not isinstance(superclass, TapoClass):
            self.error("TypeError", "superclass must be a class", node)
        klass = TapoClass(node.name, superclass)
        self.class_registry.append(klass)
        klass.is_error = bool(superclass.is_error)
        klass.module = self.current_file
        mixins = [self.eval(m, env) for m in node.mixins]
        for mixin in mixins:
            if not isinstance(mixin, TapoMixin):
                self.error("TypeError", "mixins must be mixin values", node)
            self.include_mixin(klass, mixin, node)
        self.populate_class(klass, node.members, env, node)
        env.define(node.name, klass, const=True)
        return klass

    def eval_enum(self, node, env):
        base = TapoClass(node.name, self.Object)
        base.is_enum = True
        base.module = self.current_file
        env.define(node.name, base, const=True)
        seen = set()
        for variant in node.variants:
            if variant.name in seen:
                self.error("ValueError", "duplicate enum variant '%s'" % variant.name, variant)
            seen.add(variant.name)
            variant_cls = TapoClass(variant.name, base)
            variant_cls.is_enum_variant = True
            variant_cls.enum_parent = base
            variant_cls.module = self.current_file
            if len(set(variant.fields)) != len(variant.fields):
                self.error("ValueError", "duplicate field in enum variant '%s'" % variant.name, variant)
            variant_cls.fields = [
                (field, A.Literal(None), env) for field in variant.fields
            ]
            base.statics[variant.name] = variant_cls
            env.define(variant.name, variant_cls, const=True)
        return base

    def eval_with(self, node, env):
        resource = self.eval(node.resource, env)
        body_env = Env(env)
        if node.name is not None:
            body_env.define(node.name, resource, const=True)
        if not self.responds_to(resource, "close"):
            self.error("TypeError", "with resource must respond to close", node)
        try:
            return self.eval_block(node.body, body_env)
        finally:
            self.call_value(self.get_attr(resource, "close", node), [], node)

    def include_mixin(self, klass, mixin, node):
        for name, fn in mixin.methods.items():
            klass.methods[name] = fn
        for name, fn in mixin.getters.items():
            klass.getters[name] = fn
        for name, fn in mixin.setters.items():
            klass.setters[name] = fn
        for name, fn in mixin.statics.items():
            klass.statics[name] = fn
        for spec in mixin.fields:
            self.put_field(klass, spec)
        for cls in self.class_registry:
            cls._method_cache.clear()

    def put_field(self, klass, spec):
        for i, existing in enumerate(klass.fields):
            if existing[0] == spec[0]:
                klass.fields[i] = spec
                return
        klass.fields.append(spec)

    def populate_class(self, klass, members, env, node):
        for member in members:
            if isinstance(member, A.VarDecl):
                if not isinstance(member.pattern, A.PVar):
                    self.error("ValueError", "class fields must be simple names", member)
                value = member.value if member.value is not None else A.Literal(None)
                self.put_field(klass, (member.pattern.name, value, env))
            elif isinstance(member, A.FnDecl):
                fn = self.make_method(member.name, member.params, member.body, env, klass, member)
                if member.static:
                    klass.statics[member.name] = fn
                else:
                    klass.methods[member.name] = fn
            elif isinstance(member, A.GetterDecl):
                fn = self.make_method(member.name, [], member.body, env, klass, member)
                klass.getters[member.name] = fn
            elif isinstance(member, A.SetterDecl):
                fn = self.make_method(member.name, [member.param], member.body, env, klass, member)
                klass.setters[member.name] = fn
            elif isinstance(member, A.UseAspect):
                aspect = self.eval(member.expr, env)
                if not isinstance(aspect, TapoAspect):
                    self.error("TypeError", "'use' expects an aspect", member)
                self.apply_aspect(klass, aspect, member)
            else:
                self.error("ValueError", "invalid class member", member)

    def apply_aspect(self, klass, aspect, node):
        for advice in aspect.advices:
            if advice.kind == "around":
                for other in klass.aspects:
                    if other is aspect:
                        continue
                    for existing in other.advices:
                        if existing.kind == "around" and (
                            existing.selector == advice.selector
                            or "*" in (existing.selector, advice.selector)
                        ):
                            self.error(
                                "RuntimeError",
                                "around advice conflict for selector '%s' between aspects %s and %s"
                                % (advice.selector, other.name, aspect.name),
                                node,
                            )
        klass.aspects.append(aspect)
        return klass

    def eval_mixin(self, node, env):
        mixin = TapoMixin(node.name)
        for member in node.members:
            if isinstance(member, A.VarDecl):
                if not isinstance(member.pattern, A.PVar):
                    self.error("ValueError", "mixin fields must be simple names", member)
                value = member.value if member.value is not None else A.Literal(None)
                mixin.fields.append((member.pattern.name, value, env))
            elif isinstance(member, A.FnDecl):
                fn = self.make_method(member.name, member.params, member.body, env, None, member)
                if member.static:
                    mixin.statics[member.name] = fn
                else:
                    mixin.methods[member.name] = fn
            elif isinstance(member, A.GetterDecl):
                mixin.getters[member.name] = self.make_method(
                    member.name, [], member.body, env, None, member
                )
            elif isinstance(member, A.SetterDecl):
                mixin.setters[member.name] = self.make_method(
                    member.name, [member.param], member.body, env, None, member
                )
            elif isinstance(member, A.UseAspect):
                self.error("ValueError", "mixin bodies cannot apply aspects; use the class body", member)
            else:
                self.error("ValueError", "invalid mixin member", member)
        env.define(node.name, mixin, const=True)
        return mixin

    def eval_aspect(self, node, env):
        aspect = TapoAspect(node.name)
        seen_around = set()
        for advice in node.advices:
            if advice.kind == "around":
                if advice.selector in seen_around:
                    self.error(
                        "RuntimeError",
                        "aspect %s has more than one around advice for '%s'"
                        % (node.name, advice.selector),
                        advice,
                    )
                seen_around.add(advice.selector)
            fn = TapoFunction(
                "%s.%s(%s)" % (node.name, advice.kind, advice.selector),
                advice.params,
                advice.body,
                env,
                filename=self.current_file,
                defining_class=None,
                lexical_self=None,
                is_method=False,
                line=advice.line,
            )
            aspect.advices.append(AdviceFn(advice.kind, advice.selector, fn))
        env.define(node.name, aspect, const=True)
        return aspect

    # ------------------------------------------------------------------
    # imports and modules
    # ------------------------------------------------------------------
    def std_dir(self):
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = []
        if getattr(sys, "frozen", False):
            bundle = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
            candidates.append(os.path.join(bundle, "std"))
        candidates.extend([
            os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "std"),
            os.path.join(os.path.dirname(os.path.dirname(here)), "std"),
            os.path.join(here, "stdlib"),
            os.path.join(sys.prefix, "share", "tapo", "std"),
        ])
        for candidate in candidates:
            if os.path.isdir(candidate):
                return candidate
        return candidates[0]

    def module_search_paths(self):
        paths = []
        importer = self.current_file
        if importer and not importer.startswith("<"):
            paths.append(os.path.dirname(os.path.abspath(importer)))
        paths.append(os.getcwd())
        paths.append(self.std_dir())
        paths.append(os.path.dirname(self.std_dir()))
        extra = os.environ.get("TAPO_PATH", "")
        for part in extra.split(os.pathsep):
            if part:
                paths.append(part)
        return paths

    def resolve_module_path(self, path, node):
        candidates = []
        if os.path.isabs(path):
            candidates.append(path)
        elif path.startswith("./") or path.startswith("../"):
            base = os.path.dirname(os.path.abspath(self.current_file))
            candidates.append(os.path.join(base, path))
        else:
            for base in self.module_search_paths():
                candidates.append(os.path.join(base, path))
                if path.startswith("std/"):
                    candidates.append(os.path.join(base, path[4:]))
        current = os.path.realpath(self.current_file)
        for candidate in candidates:
            if candidate.endswith(".takg") or candidate.endswith(".tapo"):
                possible = [candidate]
            else:
                possible = [candidate + ".takg", candidate + ".tapo"]
            for actual in possible:
                if not (actual.endswith(".takg") or actual.endswith(".tapo")):
                    continue
                if not os.path.isfile(actual):
                    continue
                resolved = os.path.realpath(actual)
                # A module whose name matches the importing file must not
                # import itself; keep searching the remaining search paths.
                if resolved == current:
                    continue
                return resolved
        self.error("ImportError", "cannot find module '%s' (library files use .takg)" % path, node)

    def eval_import(self, node, env):
        module = self.load_module(node.path, node)
        if node.alias:
            env.define(node.alias, module, const=True)
        else:
            for name, value in module.attrs.items():
                # Unaliased imports are convenience bindings.  Do not clobber
                # an existing name (notably the module object itself, e.g.
                # `import "random"` also exports a function called random).
                try:
                    env.lookup(name)
                    continue
                except KeyError:
                    env.define(name, value, const=True)
        return module

    def load_module(self, path, node=None):
        # Built-in modules are importable by name, e.g. import "math".
        if path.endswith(".takg"):
            builtin_name = path[:-len(".takg")]
        elif path.endswith(".tapo"):
            builtin_name = path[:-len(".tapo")]
        else:
            builtin_name = path
        if "/" not in builtin_name and "\\" not in builtin_name:
            candidate = self.globals.vars.get(builtin_name)
            if isinstance(candidate, TapoModule):
                return candidate
        resolved = self.resolve_module_path(path, node)
        self.security.check_import(self, resolved, node)
        if resolved in self.module_cache:
            return self.module_cache[resolved]
        if resolved in self.loading_modules:
            self.error("ImportError", "circular import of '%s'" % path, node)
        self.loading_modules.append(resolved)
        try:
            with open(resolved, "r", encoding="utf-8") as handle:
                source = handle.read()
            from .parser import parse

            program = parse(source, resolved)
            module_env = Env(self.globals)
            name = os.path.splitext(os.path.basename(resolved))[0]
            module_env.define("__file__", resolved, const=True)
            module_env.define("__name__", name, const=True)
            self.file_stack.append(resolved)
            try:
                try:
                    self.eval_block(program, module_env)
                except TapoReturn as ret:
                    pass
            finally:
                self.file_stack.pop()
            public = set(module_env.exports)
            for key in module_env.vars:
                if not key.startswith("_"):
                    public.add(key)
            attrs = {key: module_env.vars[key] for key in public if key in module_env.vars}
            module = TapoModule(name, resolved, attrs)
            self.module_cache[resolved] = module
            return module
        finally:
            if resolved in self.loading_modules:
                self.loading_modules.remove(resolved)

    # ------------------------------------------------------------------
    # attribute access
    # ------------------------------------------------------------------
    def get_attr(self, obj, name, node=None, auto_predicate=True):
        if isinstance(obj, TapoInstance):
            if name == "class":
                return obj.klass
            owner, getter = obj.klass.find_getter(name)
            if getter is not None:
                return self.invoke_bound(
                    TapoBoundMethod(obj, name, getter, owner, allow_aspects=False), [], node
                )
            if name in obj.fields:
                return obj.fields[name]
            owner, fn = obj.klass.find_method(name)
            if fn is not None:
                bound = TapoBoundMethod(obj, name, fn, owner, allow_aspects=True)
                return self.maybe_auto_predicate(bound, name, auto_predicate, node)
            owner, missing = obj.klass.find_method("method_missing")
            if missing is not None and name != "method_missing":
                return TapoDynamicMethod(obj, name)
            generic = self.generic_attr(obj, name)
            if generic is not _MISSING:
                return self.finish_generic(generic, name, auto_predicate, node)
            self.attribute_error(obj, name, node)
        if isinstance(obj, TapoClass):
            owner, fn = obj.find_static(name)
            if fn is not None:
                if isinstance(fn, TapoClass):
                    return fn
                return TapoBoundMethod(obj, name, fn, owner, allow_aspects=False)
            if name == "name":
                return obj.name
            if name == "superclass":
                return obj.superclass
            if name == "ancestors":
                return obj.ancestry()
            if name == "fields":
                return obj.field_names()
            if name == "methods":
                return obj.all_method_names()
            if name == "statics":
                names = set()
                for klass in obj.mro:
                    names.update(klass.statics)
                return sorted(names)
            if name == "aspects":
                return [aspect.name for aspect in obj.effective_aspects()]
            if name == "error?":
                return obj.is_error
            if name == "apply":
                def apply_aspect(interp, args):
                    if len(args) != 1 or not isinstance(args[0], TapoAspect):
                        self.error("TypeError", "apply expects one aspect", node)
                    return self.apply_aspect(obj, args[0], node)

                return TapoBuiltin("apply", apply_aspect)
            if name == "include":
                def include_mixin(interp, args):
                    if len(args) != 1 or not isinstance(args[0], TapoMixin):
                        self.error("TypeError", "include expects one mixin", node)
                    self.include_mixin(obj, args[0], node)
                    return obj

                return TapoBuiltin("include", include_mixin)
            if name == "new":
                return TapoBuiltin("new", lambda interp, args: self.instantiate(obj, args, node))
            generic = self.generic_attr(obj, name)
            if generic is not _MISSING:
                return self.finish_generic(generic, name, auto_predicate, node)
            self.attribute_error(obj, name, node)
        if isinstance(obj, TapoModule):
            if name in obj.attrs:
                return obj.attrs[name]
            if name == "name":
                return obj.name
            if name == "path":
                return obj.path
            if name == "keys":
                def module_keys(interp, args):
                    self.check_no_args("keys", args)
                    return sorted(obj.attrs.keys())
                return TapoBuiltin("keys", module_keys)
            generic = self.generic_attr(obj, name)
            if generic is not _MISSING:
                return self.finish_generic(generic, name, auto_predicate, node)
            self.attribute_error(obj, name, node)
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
        if isinstance(obj, TapoRange):
            if name == "start":
                return obj.start
            if name == "end":
                return obj.end
            if name == "inclusive?":
                return obj.inclusive
        if isinstance(obj, TapoAspect):
            if name == "name":
                return obj.name
            if name == "selectors":
                return [advice.selector for advice in obj.advices]
        if isinstance(obj, TapoMixin):
            if name == "name":
                return obj.name
        fn = B.lookup_method(obj, name)
        if fn is not None:
            bound = TapoBoundBuiltin(obj, name, fn)
            if auto_predicate and name in B.NOARG_PREDICATES:
                return self.call_value(bound, [], node)
            return bound
        generic = self.generic_attr(obj, name)
        if generic is not _MISSING:
            return self.finish_generic(generic, name, auto_predicate, node)
        self.attribute_error(obj, name, node)

    def maybe_auto_predicate(self, bound, name, auto_predicate, node):
        if not auto_predicate or not name.endswith("?"):
            return bound
        if isinstance(bound, TapoBoundMethod):
            required = len([p for p in bound.function.params if not p.is_rest and p.default is None])
            if required == 0:
                return self.invoke_bound(bound, [], node)
        return bound

    def finish_generic(self, value, name, auto_predicate, node):
        if (
            auto_predicate
            and name.endswith("?")
            and name in NOARG_GENERIC_PREDICATES
            and isinstance(value, TapoBuiltin)
        ):
            return self.call_value(value, [], node)
        return value

    def set_attr(self, obj, name, value, node=None):
        if isinstance(obj, dict):
            if name in obj:
                obj[name] = value
                return value
            self.error("AttributeError", "map has no key '%s' (use map[key] = value to add one)" % name, node)
        if isinstance(obj, TapoInstance):
            owner, setter = obj.klass.find_setter(name)
            if setter is not None:
                # A setter that assigns `self.<same-name>` is writing its
                # backing field, not recursing into itself.
                inside_same_setter = any(
                    frame.self_obj is obj and frame.method_name == name
                    for frame in reversed(self.frames)
                )
                if inside_same_setter and name in obj.fields:
                    obj.fields[name] = value
                    return value
                self.invoke_bound(
                    TapoBoundMethod(obj, name, setter, owner, allow_aspects=False), [value], node
                )
                return value
            if name in obj.fields:
                obj.fields[name] = value
                return value
            self.error(
                "AttributeError",
                "%s has no field or setter '%s'" % (obj.klass.name, name),
                node,
            )
        if isinstance(obj, TapoClass):
            self.error("AttributeError", "cannot assign class attributes directly", node)
        if isinstance(obj, TapoModule):
            self.error("AttributeError", "modules are read-only", node)
        self.error("TypeError", "%s does not support attribute assignment" % self.type_name(obj), node)

    def attribute_error(self, obj, name, node):
        kind = self.type_name(obj)
        suggestions = []
        if isinstance(obj, TapoInstance):
            suggestions = difflib.get_close_matches(name, obj.klass.all_method_names() + list(obj.fields), n=1)
        elif isinstance(obj, TapoClass):
            suggestions = difflib.get_close_matches(name, obj.all_method_names() + list(obj.statics), n=1)
        elif isinstance(obj, TapoModule):
            suggestions = difflib.get_close_matches(name, list(obj.attrs), n=1)
        else:
            suggestions = difflib.get_close_matches(name, B.method_names(obj), n=1)
        hint = " (did you mean '%s'?)" % suggestions[0] if suggestions else ""
        self.error("AttributeError", "%s has no attribute '%s'%s" % (kind, name, hint), node)

    def tapo_hash(self, value):
        if isinstance(value, list):
            return hash(tuple(self.tapo_hash(item) for item in value))
        if isinstance(value, dict):
            return hash(tuple(sorted((self.tapo_hash(k), self.tapo_hash(v)) for k, v in value.items())))
        if isinstance(value, TapoInstance):
            return id(value)
        try:
            return hash(value)
        except TypeError:
            return id(value)

    def generic_attr(self, obj, name):
        if name == "class":
            return self.class_of(obj)
        if name == "to_s":
            return TapoBuiltin("to_s", lambda interp, args: self.check_no_args("to_s", args) or self.to_s(obj))
        if name == "inspect":
            return TapoBuiltin("inspect", lambda interp, args: self.check_no_args("inspect", args) or self.inspect(obj))
        if name == "nil?":
            return TapoBuiltin("nil?", lambda interp, args: self.check_no_args("nil?", args) or obj is None)
        if name == "responds_to?":
            def responds(interp, args):
                self.check_arity("responds_to?", args, 1)
                return self.responds_to(obj, args[0])

            return TapoBuiltin("responds_to?", responds)
        if name == "methods":
            return TapoBuiltin("methods", lambda interp, args: self.check_no_args("methods", args) or self.method_names(obj))
        if name == "send":
            def send(interp, args):
                if not args:
                    self.error("ArgumentError", "send expects a method name", None)
                method_name = args[0]
                if not isinstance(method_name, str):
                    self.error("TypeError", "send expects a string method name", None)
                target = self.get_attr(obj, method_name, None, auto_predicate=False)
                return self.call_value(target, args[1:], None)

            return TapoBuiltin("send", send)
        if name == "is_a?":
            def is_a(interp, args):
                self.check_arity("is_a?", args, 1)
                if not isinstance(args[0], TapoClass):
                    self.error("TypeError", "is_a? expects a class", None)
                return self.class_of(obj).is_subclass_of(args[0])

            return TapoBuiltin("is_a?", is_a)
        if name == "instance_of?":
            def instance_of(interp, args):
                self.check_arity("instance_of?", args, 1)
                if not isinstance(args[0], TapoClass):
                    self.error("TypeError", "instance_of? expects a class", None)
                return self.class_of(obj) is args[0]

            return TapoBuiltin("instance_of?", instance_of)
        if name == "equal?":
            def equal(interp, args):
                self.check_arity("equal?", args, 1)
                return obj is args[0]

            return TapoBuiltin("equal?", equal)
        if name == "hash":
            def hash_value(interp, args):
                self.check_no_args("hash", args)
                return self.tapo_hash(obj)

            return TapoBuiltin("hash", hash_value)
        if name == "tap":
            def tap(interp, args):
                self.check_arity("tap", args, 1)
                self.call_value(args[0], [obj], None)
                return obj

            return TapoBuiltin("tap", tap)
        if name == "then":
            def then(interp, args):
                self.check_arity("then", args, 1)
                return self.call_value(args[0], [obj], None)

            return TapoBuiltin("then", then)
        if name == "dup":
            def dup(interp, args):
                self.check_no_args("dup", args)
                if isinstance(obj, TapoInstance):
                    return TapoInstance(obj.klass, dict(obj.fields))
                if isinstance(obj, list):
                    return list(obj)
                if isinstance(obj, dict):
                    return dict(obj)
                return obj

            return TapoBuiltin("dup", dup)
        return _MISSING

    def check_arity(self, name, args, count):
        if len(args) != count:
            self.error(
                "ArgumentError",
                "%s expects %d argument(s), got %d" % (name, count, len(args)),
                None,
            )

    def check_no_args(self, name, args):
        if args:
            self.error("ArgumentError", "%s expects no arguments" % name, None)

    def responds_to(self, obj, name):
        if not isinstance(name, str):
            return False
        if isinstance(obj, TapoInstance):
            if name in obj.fields or name == "class":
                return True
            if obj.klass.find_method(name)[1] is not None:
                return True
            if obj.klass.find_getter(name)[1] is not None:
                return True
            if obj.klass.find_setter(name)[1] is not None:
                return True
            if obj.klass.find_method("method_missing")[1] is not None:
                return True
            return self.generic_attr(obj, name) is not _MISSING
        if isinstance(obj, TapoClass):
            if obj.find_static(name)[1] is not None:
                return True
            if name in ("name", "superclass", "ancestors", "fields", "methods", "apply", "new", "include", "aspects", "error?", "statics"):
                return True
            return self.generic_attr(obj, name) is not _MISSING
        if isinstance(obj, TapoModule):
            return name in obj.attrs or name in ("name", "path", "keys")
        if isinstance(obj, TapoRange) and name in ("start", "end", "inclusive?"):
            return True
        if isinstance(obj, TapoAspect) and name in ("name", "selectors"):
            return True
        if isinstance(obj, TapoMixin) and name == "name":
            return True
        if B.lookup_method(obj, name) is not None:
            return True
        return self.generic_attr(obj, name) is not _MISSING

    def method_names(self, obj):
        names = set()
        if isinstance(obj, TapoInstance):
            names.update(obj.klass.all_method_names())
            names.update(obj.fields)
            if obj.klass.find_method("method_missing")[1] is not None:
                names.add("method_missing")
            names.update(self.generic_names())
        elif isinstance(obj, TapoClass):
            names.update(obj.all_method_names())
            names.update(obj.statics)
            names.update(
                ("name", "superclass", "ancestors", "fields", "methods", "apply", "new", "include", "aspects", "error?", "statics")
            )
            names.update(self.generic_names())
        elif isinstance(obj, TapoModule):
            names.update(obj.attrs)
            names.update(("name", "path", "keys"))
            names.update(self.generic_names())
        else:
            names.update(B.method_names(obj))
            names.update(self.generic_names())
        names.add("class")
        return sorted(names)

    def generic_names(self):
        return {
            "class",
            "to_s",
            "inspect",
            "nil?",
            "responds_to?",
            "methods",
            "send",
            "is_a?",
            "instance_of?",
            "equal?",
            "hash",
            "tap",
            "then",
            "dup",
        }

    # ------------------------------------------------------------------
    # indexing
    # ------------------------------------------------------------------
    def get_index(self, obj, index, node=None):
        if isinstance(obj, TapoInstance):
            if obj.klass.find_method("get")[1] is not None:
                return self.invoke_method(obj, "get", [index], node)
            self.error("TypeError", "%s does not support indexing" % obj.klass.name, node)
        if isinstance(obj, list):
            if isinstance(index, TapoRange):
                return obj[self.slice_from_range(index)]
            if not self.is_int(index):
                self.error("TypeError", "list index must be an integer", node)
            try:
                return obj[index]
            except IndexError:
                self.error("IndexError", "index %d is out of range for a list of size %d" % (index, len(obj)), node)
        if isinstance(obj, str):
            if isinstance(index, TapoRange):
                return obj[self.slice_from_range(index)]
            if not self.is_int(index):
                self.error("TypeError", "string index must be an integer", node)
            try:
                return obj[index]
            except IndexError:
                self.error("IndexError", "index %d is out of range for a string of size %d" % (index, len(obj)), node)
        if isinstance(obj, dict):
            try:
                return obj[index]
            except KeyError:
                self.error("KeyError", "key %s not found" % self.inspect(index), node)
        if isinstance(obj, TapoRange):
            values = list(self.iter_values(obj, node))
            try:
                return values[index]
            except IndexError:
                self.error("IndexError", "range index is out of bounds", node)
        self.error("TypeError", "%s does not support indexing" % self.type_name(obj), node)

    def set_index(self, obj, index, value, node=None):
        if isinstance(obj, TapoInstance):
            if obj.klass.find_method("set")[1] is not None:
                self.invoke_method(obj, "set", [index, value], node)
                return value
            self.error("TypeError", "%s does not support index assignment" % obj.klass.name, node)
        if isinstance(obj, list):
            if not self.is_int(index):
                self.error("TypeError", "list index must be an integer", node)
            try:
                obj[index] = value
            except IndexError:
                self.error("IndexError", "index %d is out of range for a list of size %d" % (index, len(obj)), node)
            return value
        if isinstance(obj, dict):
            obj[index] = value
            return value
        if isinstance(obj, str):
            self.error("TypeError", "strings are immutable", node)
        self.error("TypeError", "%s does not support index assignment" % self.type_name(obj), node)

    def slice_from_range(self, rng):
        start = rng.start
        end = rng.end
        if not self.is_int(start) or not self.is_int(end):
            self.error("TypeError", "slice bounds must be integers", None)
        return slice(start, end + 1 if rng.inclusive else end)

    # ------------------------------------------------------------------
    # operators
    # ------------------------------------------------------------------
    def is_int(self, value):
        return isinstance(value, int) and not isinstance(value, bool)

    def is_number(self, value):
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)

    def binary_op(self, op, left, right, node=None):
        if op == "is":
            if not isinstance(right, TapoClass):
                self.error("TypeError", "'is' expects a class on the right", node)
            return self.class_of(left).is_subclass_of(right)
        if op == "in":
            return self.contains(right, left, node)
        if op == "==":
            return self.tapo_equals(left, right, node)
        if op == "!=":
            return not self.tapo_equals(left, right, node)
        if op in ("..", "..."):
            if not self.is_number(left) or not self.is_number(right):
                self.error("TypeError", "range bounds must be numbers", node)
            return TapoRange(left, right, inclusive=(op == ".."))
        if isinstance(left, TapoInstance):
            owner, fn = left.klass.find_method(op)
            if fn is not None:
                bound = TapoBoundMethod(left, op, fn, owner, allow_aspects=True)
                return self.invoke_bound(bound, [right], node)
        if op == "+":
            if self.is_number(left) and self.is_number(right):
                return left + right
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, list):
                return list(left) + list(right)
            if isinstance(left, TapoRange) and isinstance(right, TapoRange):
                return list(self.iter_values(left, node)) + list(self.iter_values(right, node))
            self.type_error_binary(op, left, right, node)
        if op == "-":
            if self.is_number(left) and self.is_number(right):
                return left - right
            if isinstance(left, list) and isinstance(right, list):
                return [item for item in left if not any(self.tapo_equals(item, other) for other in right)]
            self.type_error_binary(op, left, right, node)
        if op == "*":
            if self.is_number(left) and self.is_number(right):
                return left * right
            if isinstance(left, str) and self.is_int(right):
                return left * right
            if isinstance(left, list) and self.is_int(right):
                return list(left) * right
            self.type_error_binary(op, left, right, node)
        if op == "/":
            if self.is_number(left) and self.is_number(right):
                if right == 0:
                    self.error("ZeroDivisionError", "division by zero", node)
                return left / right
            self.type_error_binary(op, left, right, node)
        if op == "//":
            if self.is_number(left) and self.is_number(right):
                if right == 0:
                    self.error("ZeroDivisionError", "division by zero", node)
                return left // right
            self.type_error_binary(op, left, right, node)
        if op == "%":
            if self.is_number(left) and self.is_number(right):
                if right == 0:
                    self.error("ZeroDivisionError", "modulo by zero", node)
                return left % right
            if isinstance(left, str):
                return self.format_string(left, right, node)
            self.type_error_binary(op, left, right, node)
        if op == "**":
            if self.is_number(left) and self.is_number(right):
                try:
                    return left ** right
                except ZeroDivisionError:
                    self.error("ZeroDivisionError", "zero cannot be raised to a negative power", node)
            self.type_error_binary(op, left, right, node)
        if op in ("<", "<=", ">", ">="):
            cmp = self.compare_values(left, right, node)
            if op == "<":
                return cmp < 0
            if op == "<=":
                return cmp <= 0
            if op == ">":
                return cmp > 0
            return cmp >= 0
        if op in ("&", "|", "^", "<<", ">>"):
            if not self.is_int(left) or not self.is_int(right):
                self.error("TypeError", "operator %s expects integers" % op, node)
            if op in ("<<", ">>") and right < 0:
                self.error("ValueError", "shift amount cannot be negative", node)
            if op == "&":
                return left & right
            if op == "|":
                return left | right
            if op == "^":
                return left ^ right
            if op == "<<":
                return left << right
            return left >> right
        self.error("ValueError", "unsupported operator '%s'" % op, node)

    def type_error_binary(self, op, left, right, node):
        self.error(
            "TypeError",
            "operator %s is not defined for %s and %s"
            % (op, self.type_name(left), self.type_name(right)),
            node,
        )

    def unary_op(self, op, value, node=None):
        if op in ("not", "!"):
            return not self.truthy(value)
        if op == "-":
            if self.is_number(value):
                return -value
            self.error("TypeError", "unary - expects a number, got %s" % self.type_name(value), node)
        if op == "+":
            if self.is_number(value):
                return +value
            self.error("TypeError", "unary + expects a number, got %s" % self.type_name(value), node)
        if op == "~":
            if self.is_int(value):
                return ~value
            self.error("TypeError", "unary ~ expects an integer, got %s" % self.type_name(value), node)
        self.error("ValueError", "unsupported unary operator '%s'" % op, node)

    def format_string(self, template, value, node):
        # A small printf-ish convenience: "%s" and "%d" placeholders.
        if isinstance(value, list):
            values = list(value)
        else:
            values = [value]
        out = []
        vi = 0
        i = 0
        while i < len(template):
            ch = template[i]
            if ch == "%" and i + 1 < len(template):
                code = template[i + 1]
                if code == "%":
                    out.append("%")
                    i += 2
                    continue
                if code in ("s", "d", "f"):
                    if vi >= len(values):
                        self.error("ValueError", "not enough values for string format", node)
                    val = values[vi]
                    vi += 1
                    if code == "s":
                        out.append(self.to_s(val))
                    elif code == "d":
                        if not self.is_int(val):
                            self.error("TypeError", "%%d expects an integer", node)
                        out.append(str(val))
                    else:
                        if not self.is_number(val):
                            self.error("TypeError", "%%f expects a number", node)
                        out.append("%f" % val)
                    i += 2
                    continue
            out.append(ch)
            i += 1
        if vi < len(values):
            self.error("ValueError", "too many values for string format", node)
        return "".join(out)

    def compare_values(self, left, right, node=None):
        if self.is_number(left) and self.is_number(right):
            return (left > right) - (left < right)
        if isinstance(left, str) and isinstance(right, str):
            return (left > right) - (left < right)
        if isinstance(left, bool) and isinstance(right, bool):
            return (left > right) - (left < right)
        if isinstance(left, list) and isinstance(right, list):
            for a, b in zip(left, right):
                if not self.tapo_equals(a, b, node):
                    return self.compare_values(a, b, node)
            return (len(left) > len(right)) - (len(left) < len(right))
        self.error(
            "TypeError",
            "cannot compare %s and %s" % (self.type_name(left), self.type_name(right)),
            node,
        )

    def tapo_equals(self, left, right, node=None):
        if left is right:
            return True
        if isinstance(left, TapoInstance) and left.klass.is_enum_variant:
            if not isinstance(right, TapoInstance) or right.klass is not left.klass:
                return False
            return all(
                self.tapo_equals(left.fields.get(field), right.fields.get(field), node)
                for field in left.klass.field_names()
            )
        if isinstance(left, TapoInstance):
            owner, fn = left.klass.find_method("==")
            if fn is not None:
                bound = TapoBoundMethod(left, "==", fn, owner, allow_aspects=True)
                return self.truthy(self.invoke_bound(bound, [right], node))
            owner, fn = left.klass.find_method("eq")
            if fn is not None:
                bound = TapoBoundMethod(left, "eq", fn, owner, allow_aspects=True)
                return self.truthy(self.invoke_bound(bound, [right], node))
            return False
        if isinstance(right, TapoInstance):
            owner, fn = right.klass.find_method("==")
            if fn is not None:
                bound = TapoBoundMethod(right, "==", fn, owner, allow_aspects=True)
                return self.truthy(self.invoke_bound(bound, [left], node))
            owner, fn = right.klass.find_method("eq")
            if fn is not None:
                bound = TapoBoundMethod(right, "eq", fn, owner, allow_aspects=True)
                return self.truthy(self.invoke_bound(bound, [left], node))
            return False
        if isinstance(left, bool) or isinstance(right, bool):
            return left is right
        if self.is_number(left) and self.is_number(right):
            return left == right
        if isinstance(left, str) and isinstance(right, str):
            return left == right
        if isinstance(left, list) and isinstance(right, list):
            return len(left) == len(right) and all(
                self.tapo_equals(a, b, node) for a, b in zip(left, right)
            )
        if isinstance(left, dict) and isinstance(right, dict):
            if len(left) != len(right):
                return False
            for key, value in left.items():
                if key not in right:
                    return False
                if not self.tapo_equals(value, right[key], node):
                    return False
            return True
        if isinstance(left, TapoRange) and isinstance(right, TapoRange):
            return (
                self.tapo_equals(left.start, right.start, node)
                and self.tapo_equals(left.end, right.end, node)
                and left.inclusive == right.inclusive
            )
        if isinstance(left, TapoClass) and isinstance(right, TapoClass):
            return left is right
        if isinstance(left, TapoFunction) or isinstance(right, TapoFunction):
            return left is right
        return False

    def contains(self, container, item, node=None):
        if isinstance(container, str):
            if not isinstance(item, str):
                self.error("TypeError", "string membership expects a string", node)
            return item in container
        if isinstance(container, list):
            return any(self.tapo_equals(item, other, node) for other in container)
        if isinstance(container, dict):
            return item in container
        if isinstance(container, TapoRange):
            if not self.is_number(item):
                return False
            if container.start <= container.end:
                if container.inclusive:
                    return container.start <= item <= container.end
                return container.start <= item < container.end
            if container.inclusive:
                return container.end <= item <= container.start
            return container.end < item <= container.start
        if isinstance(container, TapoInstance):
            owner, fn = container.klass.find_method("contains")
            if fn is not None:
                bound = TapoBoundMethod(container, "contains", fn, owner, allow_aspects=True)
                return self.truthy(self.invoke_bound(bound, [item], node))
        self.error(
            "TypeError",
            "'in' is not supported for %s" % self.type_name(container),
            node,
        )

    # ------------------------------------------------------------------
    # patterns
    # ------------------------------------------------------------------
    def resolve_dotted(self, env, name, node):
        parts = name.split(".")
        value = self.lookup_name(parts[0], env, node)
        for part in parts[1:]:
            value = self.get_attr(value, part, node, auto_predicate=False)
        return value

    def match_pattern(self, pattern, value, env):
        if isinstance(pattern, A.PWildcard):
            return {}
        if isinstance(pattern, A.PVar):
            return {pattern.name: value}
        if isinstance(pattern, A.PRange):
            if not self.is_number(value):
                return None
            if pattern.inclusive:
                return {} if pattern.start <= value <= pattern.end else None
            return {} if pattern.start <= value < pattern.end else None
        if isinstance(pattern, A.PLiteral):
            return {} if self.tapo_equals(pattern.value, value) else None
        if isinstance(pattern, A.PList):
            if not isinstance(value, list):
                return None
            items = pattern.items
            bindings = {}
            if pattern.rest is None:
                if len(value) != len(items):
                    return None
            elif len(value) < len(items):
                return None
            for subpattern, item in zip(items, value):
                found = self.match_pattern(subpattern, item, env)
                if found is None:
                    return None
                bindings.update(found)
            if pattern.rest is not None:
                bindings[pattern.rest] = list(value[len(items) :])
            return bindings
        if isinstance(pattern, A.PMap):
            if not isinstance(value, dict):
                return None
            bindings = {}
            used = set()
            for key, subpattern in pattern.pairs:
                actual_key = key.value if isinstance(key, A.Literal) else key
                if actual_key not in value:
                    return None
                found = self.match_pattern(subpattern, value[actual_key], env)
                if found is None:
                    return None
                bindings.update(found)
                used.add(actual_key)
            if pattern.rest is not None:
                bindings[pattern.rest] = {
                    key: item for key, item in value.items() if key not in used
                }
            return bindings
        if isinstance(pattern, A.PClass):
            klass = self.resolve_dotted(env, pattern.name, pattern)
            if not isinstance(klass, TapoClass):
                self.error("TypeError", "%s is not a class" % pattern.name, pattern)
            if klass.native is not None:
                if pattern.args or pattern.kwargs:
                    return None
                return {} if self.class_of(value) is klass else None
            if klass is self.Object:
                return {}
            if not isinstance(value, TapoInstance) or not value.klass.is_subclass_of(klass):
                return None
            field_names = value.klass.field_names()
            keyword_names = {key for key, _ in pattern.kwargs}
            positional_fields = [name for name in field_names if name not in keyword_names]
            bindings = {}
            if len(pattern.args) > len(positional_fields):
                return None
            for subpattern, field_name in zip(pattern.args, positional_fields):
                if field_name not in value.fields:
                    return None
                found = self.match_pattern(subpattern, value.fields[field_name], env)
                if found is None:
                    return None
                bindings.update(found)
            for field_name, subpattern in pattern.kwargs:
                if field_name not in value.fields:
                    return None
                found = self.match_pattern(subpattern, value.fields[field_name], env)
                if found is None:
                    return None
                bindings.update(found)
            return bindings
        if isinstance(pattern, A.POr):
            for alternative in pattern.alts:
                found = self.match_pattern(alternative, value, env)
                if found is not None:
                    return found
            return None
        if isinstance(pattern, A.PAs):
            found = self.match_pattern(pattern.pattern, value, env)
            if found is None:
                return None
            found[pattern.name] = value
            return found
        self.error("ValueError", "invalid pattern", pattern)

    def declare_pattern(self, pattern, value, env, const, node=None):
        if isinstance(pattern, A.PVar):
            env.define(pattern.name, value, const=const)
            return
        bindings = self.match_pattern(pattern, value, env)
        if bindings is None:
            self.error(
                "ValueError",
                "value %s does not match pattern %s"
                % (self.inspect(value), self.pattern_text(pattern)),
                node,
            )
        for name, bound in bindings.items():
            env.define(name, bound, const=const)

    def pattern_text(self, pattern):
        if isinstance(pattern, A.PWildcard):
            return "_"
        if isinstance(pattern, A.PVar):
            return pattern.name
        if isinstance(pattern, A.PLiteral):
            return self.inspect(pattern.value)
        if isinstance(pattern, A.PList):
            parts = [self.pattern_text(item) for item in pattern.items]
            if pattern.rest:
                parts.append("..." + pattern.rest)
            return "[" + ", ".join(parts) + "]"
        if isinstance(pattern, A.PMap):
            parts = ["%s: %s" % (key, self.pattern_text(sub)) for key, sub in pattern.pairs]
            if pattern.rest:
                parts.append("..." + pattern.rest)
            return "{" + ", ".join(parts) + "}"
        if isinstance(pattern, A.PClass):
            parts = [self.pattern_text(item) for item in pattern.args]
            parts.extend("%s: %s" % (key, self.pattern_text(sub)) for key, sub in pattern.kwargs)
            return pattern.name + "(" + ", ".join(parts) + ")"
        if isinstance(pattern, A.POr):
            return " | ".join(self.pattern_text(item) for item in pattern.alts)
        if isinstance(pattern, A.PAs):
            return "%s as %s" % (self.pattern_text(pattern.pattern), pattern.name)
        return "?"

    def pattern_names(self, pattern):
        if isinstance(pattern, A.PVar):
            return [pattern.name]
        if isinstance(pattern, A.PList):
            out = []
            for item in pattern.items:
                out.extend(self.pattern_names(item))
            if pattern.rest:
                out.append(pattern.rest)
            return out
        if isinstance(pattern, A.PMap):
            out = []
            for _, item in pattern.pairs:
                out.extend(self.pattern_names(item))
            if pattern.rest:
                out.append(pattern.rest)
            return out
        if isinstance(pattern, A.PClass):
            out = []
            for item in pattern.args:
                out.extend(self.pattern_names(item))
            for _, item in pattern.kwargs:
                out.extend(self.pattern_names(item))
            return out
        if isinstance(pattern, A.POr):
            out = []
            for item in pattern.alts:
                for name in self.pattern_names(item):
                    if name not in out:
                        out.append(name)
            return out
        if isinstance(pattern, A.PAs):
            return self.pattern_names(pattern.pattern) + [pattern.name]
        return []

    def declared_names(self, decl):
        if isinstance(decl, A.Identifier):
            return [decl.name]
        if isinstance(decl, A.VarDecl):
            return self.pattern_names(decl.pattern)
        if isinstance(decl, (A.FnDecl, A.ClassDecl, A.MixinDecl, A.AspectDecl, A.EnumDecl)):
            return [decl.name]
        return []

    # ------------------------------------------------------------------
    # names and classes
    # ------------------------------------------------------------------
    def lookup_name(self, name, env, node=None, auto_predicate=True):
        try:
            return env.lookup(name)
        except KeyError:
            pass
        frame = self.frames[-1] if self.frames else None
        if frame is not None and frame.self_obj is not None:
            if self.responds_to(frame.self_obj, name):
                return self.get_attr(frame.self_obj, name, node, auto_predicate=auto_predicate)
        nearby = env.names()
        if frame is not None and frame.self_obj is not None:
            nearby = nearby + self.method_names(frame.self_obj)
        matches = difflib.get_close_matches(name, nearby, n=1)
        hint = " (did you mean '%s'?)" % matches[0] if matches else ""
        self.error("NameError", "undefined variable '%s'%s" % (name, hint), node)

    def class_of(self, value):
        if value is None:
            return self.builtin_classes["Nil"]
        if isinstance(value, bool):
            return self.builtin_classes["Bool"]
        if self.is_int(value):
            return self.builtin_classes["Int"]
        if isinstance(value, float):
            return self.builtin_classes["Float"]
        if isinstance(value, str):
            return self.builtin_classes["String"]
        if isinstance(value, list):
            return self.builtin_classes["List"]
        if isinstance(value, dict):
            return self.builtin_classes["Map"]
        if isinstance(value, TapoInstance):
            return value.klass
        if isinstance(value, TapoClass):
            return self.class_class
        if isinstance(value, (TapoFunction, TapoBoundMethod, TapoBuiltin, TapoBoundBuiltin, TapoDynamicMethod, TapoProceed)):
            return self.function_class
        if isinstance(value, TapoModule):
            return self.builtin_classes["Module"]
        if isinstance(value, TapoRange):
            return self.builtin_classes["Range"]
        if isinstance(value, TapoGenerator):
            return self.builtin_classes["Generator"]
        if isinstance(value, TapoAspect):
            return self.builtin_classes["Aspect"]
        if isinstance(value, TapoMixin):
            return self.builtin_classes["Mixin"]
        return self.Object

    def type_name(self, value):
        return self.class_of(value).name

    def truthy(self, value):
        return value is not None and value is not False

    # ------------------------------------------------------------------
    # iteration
    # ------------------------------------------------------------------
    def iter_values(self, value, node=None):
        if isinstance(value, list):
            return iter(value)
        if isinstance(value, str):
            return iter(value)
        if isinstance(value, dict):
            return iter([[key, item] for key, item in value.items()])
        if isinstance(value, TapoRange):
            return self.iter_range(value, node)
        if isinstance(value, TapoGenerator):
            return iter(value)
        if isinstance(value, TapoInstance):
            if value.klass.find_method("each")[1] is not None:
                collected = []

                def callback(interp, args):
                    self.check_arity("each callback", args, 1)
                    collected.append(args[0])
                    return None

                self.invoke_method(value, "each", [TapoBuiltin("each_callback", callback)], node)
                return iter(collected)
            if value.klass.find_method("to_list")[1] is not None:
                return iter(self.invoke_method(value, "to_list", [], node))
        self.error("TypeError", "%s is not iterable" % self.type_name(value), node)

    def iter_range(self, rng, node=None):
        if not self.is_number(rng.start) or not self.is_number(rng.end):
            self.error("TypeError", "range bounds must be numbers", node)
        start = rng.start
        end = rng.end
        step = 1 if end >= start else -1
        inclusive = rng.inclusive
        def generate():
            current = start
            while True:
                if step > 0:
                    if current > end or (not inclusive and current == end):
                        break
                else:
                    if current < end or (not inclusive and current == end):
                        break
                yield current
                current += step
        return generate()

    # ------------------------------------------------------------------
    # errors and traces
    # ------------------------------------------------------------------
    def make_error_instance(self, class_name, message, node=None):
        klass = self.error_classes.get(class_name) or self.error_classes["RuntimeError"]
        instance = TapoInstance(klass)
        instance.fields["message"] = message
        instance.fields["trace"] = []
        instance.fields["file"] = self.current_file
        instance.fields["line"] = node.line if node is not None else 0
        return instance

    def error(self, class_name, message, node=None):
        instance = self.make_error_instance(class_name, message, node)
        raise TapoException(instance, [])

    def raise_value(self, value, node=None):
        if isinstance(value, TapoInstance) and value.klass.is_subclass_of(self.error_classes["Error"]):
            instance = value
        elif isinstance(value, TapoClass) and value.is_subclass_of(self.error_classes["Error"]):
            instance = self.instantiate(value, [], node)
        else:
            instance = self.make_error_instance("Error", self.to_s(value), node)
        instance.fields.setdefault("message", self.to_s(value))
        instance.fields.setdefault("trace", [])
        if "file" not in instance.fields:
            instance.fields["file"] = self.current_file
            instance.fields["line"] = node.line if node is not None else 0
        raise TapoException(instance, [])

    def add_note(self, exc, name, node=None):
        filename = self.current_file
        line = node.line if node is not None else 0
        self.add_note_at(exc, name, filename, line)

    def add_note_at(self, exc, name, filename, line):
        exc.add_frame(name, filename, line)
        if isinstance(exc.value, TapoInstance):
            trace = exc.value.fields.setdefault("trace", [])
            entry = "at %s (%s:%s)" % (name, filename, line)
            trace.append(entry)

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def format_float(self, value):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)

    def to_s(self, value):
        if value is None:
            return "nil"
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, str):
            return value
        if self.is_int(value):
            return str(value)
        if isinstance(value, float):
            return self.format_float(value)
        if isinstance(value, list):
            return "[" + ", ".join(self.inspect(item) for item in value) + "]"
        if isinstance(value, dict):
            return (
                "{"
                + ", ".join(
                    "%s: %s" % (self.inspect(key), self.inspect(item))
                    for key, item in value.items()
                )
                + "}"
            )
        if isinstance(value, TapoInstance) and value.klass.is_enum_variant:
            return self.enum_repr(value)
        if isinstance(value, TapoInstance):
            owner, fn = value.klass.find_method("to_s")
            if fn is not None:
                if self._inspect_depth > 12:
                    return "<...>"
                self._inspect_depth += 1
                try:
                    result = self.invoke_bound(
                        TapoBoundMethod(value, "to_s", fn, owner, allow_aspects=True), [], None
                    )
                    return result if isinstance(result, str) else self.to_s(result)
                finally:
                    self._inspect_depth -= 1
            if value.klass.is_subclass_of(self.error_classes["Error"]):
                message = value.fields.get("message", "")
                if message:
                    return "%s: %s" % (value.klass.name, message)
                return value.klass.name
            return "<%s>" % value.klass.name
        if isinstance(value, TapoClass):
            return value.name
        if isinstance(value, (TapoFunction, TapoBoundMethod, TapoBuiltin, TapoBoundBuiltin, TapoDynamicMethod, TapoProceed)):
            return "<fn %s>" % getattr(value, "name", "?")
        if isinstance(value, TapoModule):
            return "<module %s>" % value.name
        if isinstance(value, TapoRange):
            return self.range_repr(value)
        if isinstance(value, TapoAspect):
            return "<aspect %s>" % value.name
        if isinstance(value, TapoMixin):
            return "<mixin %s>" % value.name
        return str(value)

    def enum_repr(self, value):
        names = value.klass.field_names()
        parts = [self.inspect(value.fields.get(name)) for name in names]
        if not parts:
            return value.klass.name
        return "%s(%s)" % (value.klass.name, ", ".join(parts))

    def range_repr(self, rng):
        return "%s%s%s" % (
            self.to_s(rng.start),
            ".." if rng.inclusive else "...",
            self.to_s(rng.end),
        )

    def inspect(self, value):
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, list):
            if self._inspect_depth > 12:
                return "[...]"
            self._inspect_depth += 1
            try:
                return "[" + ", ".join(self.inspect(item) for item in value) + "]"
            finally:
                self._inspect_depth -= 1
        if isinstance(value, dict):
            if self._inspect_depth > 12:
                return "{...}"
            self._inspect_depth += 1
            try:
                return (
                    "{"
                    + ", ".join(
                        "%s: %s" % (self.inspect(key), self.inspect(item))
                        for key, item in value.items()
                    )
                    + "}"
                )
            finally:
                self._inspect_depth -= 1
        if isinstance(value, TapoInstance) and value.klass.is_enum_variant:
            return self.enum_repr(value)
        if isinstance(value, TapoInstance):
            owner, fn = value.klass.find_method("inspect")
            if fn is not None:
                if self._inspect_depth > 12:
                    return "<...>"
                self._inspect_depth += 1
                try:
                    result = self.invoke_bound(
                        TapoBoundMethod(value, "inspect", fn, owner, allow_aspects=True), [], None
                    )
                    return result if isinstance(result, str) else self.inspect(result)
                finally:
                    self._inspect_depth -= 1
            if value.klass.is_subclass_of(self.error_classes["Error"]):
                return "%s(%s)" % (
                    value.klass.name,
                    self.inspect(value.fields.get("message", "")),
                )
            if self._inspect_depth > 12:
                return "<%s ...>" % value.klass.name
            self._inspect_depth += 1
            try:
                names = value.klass.field_names()
                parts = []
                for name in names:
                    if name in value.fields:
                        parts.append("%s=%s" % (name, self.inspect(value.fields[name])))
                for name, item in value.fields.items():
                    if name not in names:
                        parts.append("%s=%s" % (name, self.inspect(item)))
                if len(parts) > 8:
                    parts = parts[:8] + ["..."]
                if parts:
                    return "<%s %s>" % (value.klass.name, " ".join(parts))
                return "<%s>" % value.klass.name
            finally:
                self._inspect_depth -= 1
        if isinstance(value, TapoClass):
            return "<class %s>" % value.name
        if isinstance(value, (TapoFunction, TapoBoundMethod, TapoBuiltin, TapoBoundBuiltin, TapoDynamicMethod, TapoProceed)):
            return "<fn %s>" % getattr(value, "name", "?")
        if isinstance(value, TapoModule):
            return "<module %s (%s)>" % (value.name, value.path)
        if isinstance(value, TapoRange):
            return self.range_repr(value)
        if isinstance(value, TapoAspect):
            return "<aspect %s>" % value.name
        if isinstance(value, TapoMixin):
            return "<mixin %s>" % value.name
        return self.to_s(value)

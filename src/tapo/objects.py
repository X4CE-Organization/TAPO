"""Runtime object model for TAPO.

Everything a TAPO program manipulates is represented by one of the classes in
this module: user classes and instances, functions, methods, mixins, aspects,
modules, ranges and builtin callables.
"""

from __future__ import annotations


class Frame:
    __slots__ = ("self_obj", "defining_class", "method_name")

    def __init__(self, self_obj=None, defining_class=None, method_name=None):
        self.self_obj = self_obj
        self.defining_class = defining_class
        self.method_name = method_name


class TapoClass:
    __slots__ = (
        "name",
        "superclass",
        "mro",
        "methods",
        "getters",
        "setters",
        "statics",
        "fields",
        "aspects",
        "native",
        "is_error",
        "builtin",
        "module",
    )

    def __init__(self, name, superclass=None, native=None, is_error=False, builtin=False):
        self.name = name
        self.superclass = superclass
        self.mro = [self] + (list(superclass.mro) if superclass is not None else [])
        self.methods = {}
        self.getters = {}
        self.setters = {}
        self.statics = {}
        self.fields = []  # list of (name, default_expr, defining_env)
        self.aspects = []
        self.native = native
        self.is_error = is_error
        self.builtin = builtin
        self.module = None

    def find_method(self, name):
        for klass in self.mro:
            if name in klass.methods:
                return klass, klass.methods[name]
        return None, None

    def find_getter(self, name):
        for klass in self.mro:
            if name in klass.getters:
                return klass, klass.getters[name]
        return None, None

    def find_setter(self, name):
        for klass in self.mro:
            if name in klass.setters:
                return klass, klass.setters[name]
        return None, None

    def find_static(self, name):
        for klass in self.mro:
            if name in klass.statics:
                return klass, klass.statics[name]
        return None, None

    def is_subclass_of(self, other):
        return other in self.mro

    def field_specs(self):
        """Return field specifications, base class fields first.

        A subclass field with the same name replaces the inherited default but
        keeps the original position, so positional class patterns stay stable.
        """
        merged = {}
        order = []
        for klass in reversed(self.mro):
            for spec in klass.fields:
                fname = spec[0]
                if fname not in merged:
                    order.append(fname)
                merged[fname] = spec
        return [merged[name] for name in order]

    def field_names(self):
        return [spec[0] for spec in self.field_specs()]

    def all_method_names(self):
        names = set()
        for klass in self.mro:
            names.update(klass.methods)
            names.update(klass.getters)
            names.update(klass.setters)
        return sorted(names)

    def effective_aspects(self):
        seen = set()
        out = []
        for klass in self.mro:
            for aspect in klass.aspects:
                if id(aspect) not in seen:
                    seen.add(id(aspect))
                    out.append(aspect)
        return out

    def ancestry(self):
        return list(self.mro)


class TapoMixin:
    __slots__ = ("name", "methods", "getters", "setters", "statics", "fields")

    def __init__(self, name):
        self.name = name
        self.methods = {}
        self.getters = {}
        self.setters = {}
        self.statics = {}
        self.fields = []


class TapoInstance:
    __slots__ = ("klass", "fields")

    def __init__(self, klass, fields=None):
        self.klass = klass
        self.fields = fields if fields is not None else {}

    def is_error(self):
        return self.klass.is_subclass_of(_ERROR_ROOT[0]) if _ERROR_ROOT[0] is not None else False

    def __repr__(self):
        return "<%s instance>" % self.klass.name


# Filled in by make_error_classes; lets instances check for Error ancestry.
_ERROR_ROOT = [None]


class TapoRange:
    __slots__ = ("start", "end", "inclusive")

    def __init__(self, start, end, inclusive=True):
        self.start = start
        self.end = end
        self.inclusive = inclusive

    def __repr__(self):
        return "TapoRange(%r, %r, %r)" % (self.start, self.end, self.inclusive)


class TapoModule:
    __slots__ = ("name", "path", "attrs")

    def __init__(self, name, path, attrs):
        self.name = name
        self.path = path
        self.attrs = attrs


class TapoAspect:
    __slots__ = ("name", "advices")

    def __init__(self, name):
        self.name = name
        self.advices = []  # list of AdviceFn

    def matching(self, method_name):
        return [a for a in self.advices if a.selector in ("*", method_name)]

    def around_for(self, method_name):
        found = [a for a in self.advices if a.kind == "around" and a.selector == method_name]
        return found[0] if found else None


class AdviceFn:
    __slots__ = ("kind", "selector", "function")

    def __init__(self, kind, selector, function):
        self.kind = kind
        self.selector = selector
        self.function = function


class TapoFunction:
    __slots__ = (
        "name",
        "params",
        "body",
        "closure",
        "filename",
        "defining_class",
        "lexical_self",
        "is_method",
        "line",
    )

    def __init__(
        self,
        name,
        params,
        body,
        closure,
        filename=None,
        defining_class=None,
        lexical_self=None,
        is_method=False,
        line=None,
    ):
        self.name = name
        self.params = params
        self.body = body
        self.closure = closure
        self.filename = filename
        self.defining_class = defining_class
        self.lexical_self = lexical_self
        self.is_method = is_method
        self.line = line

    def __repr__(self):
        return "<fn %s>" % self.name


class TapoBoundMethod:
    __slots__ = ("instance", "name", "function", "owner", "allow_aspects")

    def __init__(self, instance, name, function, owner, allow_aspects=True):
        self.instance = instance
        self.name = name
        self.function = function
        self.owner = owner
        self.allow_aspects = allow_aspects


class TapoDynamicMethod:
    __slots__ = ("instance", "name")

    def __init__(self, instance, name):
        self.instance = instance
        self.name = name


class TapoBuiltin:
    __slots__ = ("name", "fn")

    def __init__(self, name, fn):
        self.name = name
        self.fn = fn

    def __repr__(self):
        return "<builtin %s>" % self.name


class TapoBoundBuiltin:
    __slots__ = ("receiver", "name", "fn")

    def __init__(self, receiver, name, fn):
        self.receiver = receiver
        self.name = name
        self.fn = fn

    def __repr__(self):
        return "<builtin method %s>" % self.name


class TapoProceed:
    __slots__ = ("interpreter", "callback", "label")

    def __init__(self, interpreter, callback, label):
        self.interpreter = interpreter
        self.callback = callback
        self.label = label

    def __repr__(self):
        return "<proceed %s>" % self.label


def make_error_classes():
    """Create the builtin Error hierarchy. Returns a dict name -> TapoClass."""
    root = TapoClass("Object", None, builtin=True)
    error = TapoClass("Error", root, is_error=True, builtin=True)
    _ERROR_ROOT[0] = error
    classes = {"Object": root, "Error": error}
    hierarchy = [
        ("RuntimeError", "Error"),
        ("ArgumentError", "Error"),
        ("TypeError", "Error"),
        ("NameError", "Error"),
        ("AttributeError", "Error"),
        ("IndexError", "Error"),
        ("KeyError", "Error"),
        ("ValueError", "Error"),
        ("ZeroDivisionError", "Error"),
        ("AssertionError", "Error"),
        ("ImportError", "Error"),
        ("IOError", "Error"),
        ("MatchError", "Error"),
        ("NotImplementedError", "Error"),
        ("FrozenError", "Error"),
    ]
    for name, parent in hierarchy:
        classes[name] = TapoClass(name, classes[parent], is_error=True, builtin=True)
    return classes

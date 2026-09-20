"""注册一个属性上带描述符（property / cached_property）的插件对象，六条读数。
跑法：PYTHONPATH=src .venv/bin/python repro/property-registration.py
"""
from __future__ import annotations

import sys
from functools import cached_property

from pluggy import HookimplMarker, PluginManager

hookimpl = HookimplMarker("example")


def newpm() -> PluginManager:
    return PluginManager("example")


def call_hook(pm: PluginManager, name: str, **kwargs):
    """A hook name with zero registered impls does not exist on pm.hook
    (AttributeError) -- that counts as 'nobody was hooked up' == []."""
    try:
        return list(getattr(pm.hook, name)(**kwargs))
    except AttributeError:
        return []


def p1_no_property_evaluation() -> tuple[bool, str]:
    """Registering must not evaluate plain properties (side effects)."""
    evals = {"data": 0}

    class P:
        @property
        def data(self):
            evals["data"] += 1
            return "plain-value"

        @hookimpl
        def item(self, x):
            return x + 1

    pm = newpm()
    pm.register(P())
    res = pm.hook.item(x=1)
    ok = evals["data"] == 0 and res == [2]
    return ok, f"property 'data' evaluations during register = {evals['data']} (want 0); item -> {res!r}"


def p2_raising_property_not_fatal() -> tuple[bool, str]:
    """A property that raises must not abort register() half-way (partial state)."""

    class P:
        @hookimpl
        def aaa_good(self, x):
            return x + 1

        @property
        def zzz_boom(self):
            raise ValueError("boom")

    pm = newpm()
    err = None
    try:
        pm.register(P())
    except Exception as e:  # noqa: BLE001
        err = e
    called = None
    try:
        called = pm.hook.aaa_good(x=1)
    except Exception as e:  # noqa: BLE001
        called = f"raised {e!r}"
    ok = err is None and called == [2]
    return ok, (
        f"register raised {err!r}; plugin visible after crash = {bool(pm.get_plugins())}; "
        f"aaa_good -> {called!r}"
    )


def p3_property_hook_not_supported() -> tuple[bool, str]:
    """A hookimpl exposed through a property must NOT be registered/invoked."""
    trace: list[str] = []

    class P:
        @property
        def lazy(self):
            trace.append("evaluated")

            @hookimpl
            def impl(x):
                trace.append("invoked")
                return x * 2

            return impl

    pm = newpm()
    pm.register(P())
    res = call_hook(pm, "lazy", x=21)
    ok = res == [] and "invoked" not in trace
    return ok, f"hook.lazy -> {res!r}; trace={trace}"


def p4_bound_method_still_works() -> tuple[bool, str]:
    """Regression guard: ordinary bound-method hookimpls keep working with self."""

    class P:
        def __init__(self):
            self.seen = None

        @hookimpl
        def item(self, x):
            self.seen = x
            return "ok"

    inst = P()
    pm = newpm()
    pm.register(inst)
    res = pm.hook.item(x=5)
    ok = res == ["ok"] and inst.seen == 5
    return ok, f"item -> {res!r}; self.seen = {inst.seen!r}"


def p5_cached_property_ignored() -> tuple[bool, str]:
    """cached_property hookimpls: neither evaluated nor registered."""
    trace: list[str] = []

    class P:
        @cached_property
        def hooky(self):
            trace.append("evaluated")

            @hookimpl
            def impl(x):
                trace.append("invoked")
                return x

            return impl

    pm = newpm()
    pm.register(P())
    res = call_hook(pm, "hooky", x=3)
    ok = res == [] and not trace
    return ok, f"hook.hooky -> {res!r}; trace={trace}"


def p6_static_classmethod_keep_working() -> tuple[bool, str]:
    """static/classmethod hookimpls must remain hookable after the fix."""

    class P:
        @staticmethod
        @hookimpl
        def stat(x):
            return x + 10

        @classmethod
        @hookimpl
        def clsimpl(cls, x):
            return x + 20

    pm = newpm()
    pm.register(P())
    a = pm.hook.stat(x=1)
    b = pm.hook.clsimpl(x=1)
    ok = a == [11] and b == [21]
    return ok, f"stat -> {a!r}; clsimpl -> {b!r}"


CASES = [
    ("P1 register must not evaluate properties", p1_no_property_evaluation),
    ("P2 raising property must not abort register", p2_raising_property_not_fatal),
    ("P3 property-provided hookimpl must not be called", p3_property_hook_not_supported),
    ("P4 bound-method hookimpl still works (self bound)", p4_bound_method_still_works),
    ("P5 cached_property hookimpl ignored & unevaluated", p5_cached_property_ignored),
    ("P6 static/classmethod hookimpls still work", p6_static_classmethod_keep_working),
]


def main() -> int:
    print(f"pluggy from: {sys.modules['pluggy'].__file__}")
    failed = 0
    for label, fn in CASES:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"raised {type(e).__name__}: {e}"
        failed += not ok
        print(f"{label}: {'PASS' if ok else 'FAIL'} -- {detail}")
    print(f"TOTAL: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

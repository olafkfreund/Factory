"""The hub's own test for ``scripts/job_tracing.py`` (Factory#795).

This module is CANONICAL — hand-vendored byte-exact into AIFactory and
TFactory — and until now the hub had **no test for it at all**. That gap is
what this file closes, and it is not a hypothetical one:

Factory#744 removed ``_attach_token`` from this module as CodeQL dead code.
Inside the hub that verdict was correct on the evidence available: the value
was assigned by ``init_agent_tracing`` and read nowhere, because nothing here
read it. The only readers live in the CONSUMERS' pytest fixtures, which detach
the token so the attached span does not leak across a test session — and the
hub does not contain those. ``check_verification_core_drift.py`` compares the
module byte-for-byte and cannot see that a consumer's tests depend on a symbol
the module no longer has, so nothing went red for 68 hours.

A canonical module with no canonical test is a contract nobody can check.

**No new dependency.** ``init_agent_tracing`` imports opentelemetry inside the
function and swallows ``ImportError``, so the hub can exercise every path by
putting fakes in ``sys.modules``. Installing the real SDK here would make the
hub's test job carry a runtime dep for one module, and would test the SDK
rather than this file's contract.

**What is asserted is the CONTRACT, not the mechanism:** that a successful
attach leaves its token reachable on the module. A consumer that cannot reach
it cannot detach it, which is the failure Factory#795 describes.
"""

from __future__ import annotations

import sys
import types
from typing import Any

# scripts/ is put on sys.path by tests/conftest.py, same as every sibling
# gate test in this directory.
import job_tracing
import pytest

SAMPLE_TP = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def _reset() -> None:
    """Clear the module's latch.

    Called at the TOP of every test rather than from an autouse fixture. The
    ratchet runs mypy with --ignore-missing-imports, so ``pytest.fixture``
    resolves to ``Any`` and ``@pytest.fixture(autouse=True)`` is an untyped
    decorator under --strict. ``tests/test_pin_freshness.py`` documents the
    same constraint and reaches the same shape; no test in this repo uses a
    fixture.

    ``_initialized`` is a module-level guard, so without this the second test
    in the file would find the module already initialised and skip the work it
    means to exercise.
    """
    job_tracing._initialized = False
    job_tracing._attach_token = None
    job_tracing._job_span = None
    job_tracing._provider = None


def _install_fake_otel(monkeypatch: pytest.MonkeyPatch, token: object) -> dict[str, Any]:
    """Put a minimal opentelemetry in ``sys.modules`` and record what it saw.

    Only the surface ``init_agent_tracing`` actually imports is provided. A
    fake that offered more would drift from the real package without anything
    noticing.
    """
    seen: dict[str, Any] = {}

    def attach(context: object) -> object:
        seen["attached"] = context
        return token

    span = types.SimpleNamespace(
        end=lambda: None, set_status=lambda *_a, **_k: None, is_recording=lambda: True
    )

    class _Tracer:
        def start_span(self, *_args: Any, **_kwargs: Any) -> Any:
            return span

    class _Provider:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def add_span_processor(self, *args: Any, **kwargs: Any) -> None:
            pass

        def shutdown(self, *args: Any, **kwargs: Any) -> None:
            pass

    mods = {
        "opentelemetry": types.ModuleType("opentelemetry"),
        "opentelemetry.context": types.ModuleType("opentelemetry.context"),
        "opentelemetry.sdk": types.ModuleType("opentelemetry.sdk"),
        "opentelemetry.sdk.resources": types.ModuleType("opentelemetry.sdk.resources"),
        "opentelemetry.sdk.trace": types.ModuleType("opentelemetry.sdk.trace"),
        "opentelemetry.sdk.trace.export": types.ModuleType("opentelemetry.sdk.trace.export"),
        "opentelemetry.trace": types.ModuleType("opentelemetry.trace"),
        "opentelemetry.trace.propagation": types.ModuleType("opentelemetry.trace.propagation"),
        "opentelemetry.trace.propagation.tracecontext": types.ModuleType(
            "opentelemetry.trace.propagation.tracecontext"
        ),
    }
    trace_mod = mods["opentelemetry.trace"]
    trace_mod.get_tracer = lambda *_a, **_k: _Tracer()  # type: ignore[attr-defined]
    trace_mod.set_span_in_context = lambda span, _ctx=None: {"span": span}  # type: ignore[attr-defined]
    trace_mod.get_tracer_provider = object  # type: ignore[attr-defined]
    trace_mod.set_tracer_provider = lambda _p: None  # type: ignore[attr-defined]
    mods["opentelemetry"].trace = trace_mod  # type: ignore[attr-defined]
    mods["opentelemetry.context"].attach = attach  # type: ignore[attr-defined]
    mods["opentelemetry.context"].detach = lambda t: seen.__setitem__("detached", t)  # type: ignore[attr-defined]
    mods["opentelemetry.sdk.resources"].Resource = types.SimpleNamespace(  # type: ignore[attr-defined]
        create=lambda d: d
    )
    mods["opentelemetry.sdk.trace"].TracerProvider = _Provider  # type: ignore[attr-defined]

    class _Propagator:
        def extract(self, carrier: dict[str, str]) -> dict[str, str]:
            seen["extracted"] = carrier
            return carrier

    mods["opentelemetry.trace.propagation.tracecontext"].TraceContextTextMapPropagator = (  # type: ignore[attr-defined]
        _Propagator
    )

    for name, mod in mods.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return seen


def test_no_traceparent_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standalone CLI runs: no env var, no work, no token."""
    _reset()
    monkeypatch.delenv("TRACEPARENT", raising=False)
    job_tracing.init_agent_tracing()
    assert job_tracing._initialized is True
    assert job_tracing._attach_token is None


def test_empty_traceparent_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty env var is absence, not a malformed value."""
    _reset()
    monkeypatch.setenv("TRACEPARENT", "")
    job_tracing.init_agent_tracing()
    assert job_tracing._initialized is True
    assert job_tracing._attach_token is None


def test_missing_opentelemetry_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """The import guard: a process without the SDK runs untraced, not broken."""
    _reset()
    monkeypatch.setenv("TRACEPARENT", SAMPLE_TP)
    for name in [m for m in sys.modules if m == "opentelemetry" or m.startswith("opentelemetry.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_BlockOtel(), *sys.meta_path])
    job_tracing.init_agent_tracing()
    assert job_tracing._initialized is True
    assert job_tracing._attach_token is None


class _BlockOtel:
    """Make ``import opentelemetry`` raise ImportError for the guard test."""

    def find_module(self, _fullname: str, _path: object = None) -> None:
        """Legacy hook; present so older import machinery does not fall back."""

    def find_spec(self, fullname: str, _path: object = None, _target: object = None) -> None:
        if fullname == "opentelemetry" or fullname.startswith("opentelemetry."):
            raise ImportError(fullname)


def test_a_successful_attach_leaves_its_token_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE CONTRACT Factory#795 is about.

    A consumer's pytest fixture detaches this token so the attached span does
    not leak into every later test in the session. It can only do that if the
    token is reachable on the module after ``init_agent_tracing`` runs.

    Asserting it is not None is deliberately weaker than asserting a
    particular value: what a consumer needs is a handle it can pass to
    ``detach``, not a specific representation.
    """
    _reset()
    sentinel = object()
    seen = _install_fake_otel(monkeypatch, sentinel)
    monkeypatch.setenv("TRACEPARENT", SAMPLE_TP)

    job_tracing.init_agent_tracing()

    assert job_tracing._initialized is True
    assert job_tracing._attach_token is sentinel, (
        "init_agent_tracing attached a context but did not keep the token. "
        "A consumer cannot detach what it cannot reach -- see Factory#795."
    )
    assert seen["extracted"] == {"traceparent": SAMPLE_TP}


def test_init_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second call must not attach a second context.

    Two tokens would mean one is unreachable, and a consumer detaching the
    one it can see would leave the other attached -- the leak with extra steps.
    """
    _reset()
    first = object()
    _install_fake_otel(monkeypatch, first)
    monkeypatch.setenv("TRACEPARENT", SAMPLE_TP)

    job_tracing.init_agent_tracing()
    token_after_first = job_tracing._attach_token

    _install_fake_otel(monkeypatch, object())
    job_tracing.init_agent_tracing()

    assert job_tracing._attach_token is token_after_first

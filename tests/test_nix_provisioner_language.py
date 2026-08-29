"""A DECLARED `language` must get its own toolchain, or none at all (Factory#1012).

`generate_flake` branched on `go` and let everything else fall through to the
Python harness, so `{"language": "rust", "verify_commands": ["cargo test"]}`
produced a devShell whose entire package list was `pkgs.python313`. The flake
evaluated, the shell realised, and `cargo test` then died with "command not
found" -- a RUNNER failure reported where a test result belongs, which reads as
flakiness. Same symptom class as Factory#1007 and #1009.

It failed OPEN, which is what made it expensive. An unknown language producing
an empty or erroring shell would have been obvious on the first run; producing a
*working Python shell* pushed the failure hours downstream, into a place where
it looks like an environment problem rather than a provisioning one.

The distinction these tests pin, in both directions:

  * ABSENT language -> Python. Deliberate, unchanged, and load-bearing: a
    manifest that omits `language` has always meant "give me the pytest
    harness", and plenty of them do.
  * DECLARED-but-unknown -> ProvisionError. A language the generator was never
    taught is a statement it cannot honour, not a request for the default.

Proven by evaluating the generated flakes and FORCING the derivation
(`nix eval ... .drvPath`), then running the declared binary in the shell
(`nix develop --command cargo --version`) -- against nixpkgs 567a49d1. Both
halves are needed: `nix eval` of the shell's NAME passes on a flake that cannot
build (the package list is lazy), and a flake that evaluates can still lack the
binary the lane needs, which is exactly this bug.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from nix_provisioner import ProvisionError, generate_flake


def _flake(**env: object) -> str:
    env.setdefault("provisioning", {"method": "nix", "generated": True})
    flake: str = generate_flake(env)
    return flake


def _has_attr(flake: str, attr: str) -> bool:
    """Word-boundary attr match.

    A plain `"pkgs.python" in flake` matches the legitimate `pkgs.python313`,
    and `"pkgs.dotnet"` matches `pkgs.dotnet-sdk`. Both mistakes were made on
    this component this week, in both directions -- a false pass and a false
    fail. `[\\w-]` excludes the digits AND the hyphen, so `pkgs.dotnet` does not
    match `pkgs.dotnet-sdk` while `pkgs.dotnet-sdk` still matches itself.
    """
    return re.search(rf"pkgs\.{re.escape(attr)}(?![\w-])", flake) is not None


# ── the declared toolchains ─────────────────────────────────────────────────


def test_rust_gets_cargo_not_python() -> None:
    """The reported case verbatim. `cargo test` cannot run in a Python shell."""
    f = _flake(language="rust", verify_commands=["cargo test"])

    assert _has_attr(f, "rustc")
    assert _has_attr(f, "cargo")
    # The regression itself: python313 was the ENTIRE package list here.
    assert not _has_attr(f, "python313")


def test_java_gets_a_jdk_not_python() -> None:
    f = _flake(language="java", verify_commands=["mvn test"])

    assert _has_attr(f, "jdk21")
    assert _has_attr(f, "maven")
    assert not _has_attr(f, "python313")


def test_dotnet_and_its_spellings_get_the_sdk() -> None:
    """`dotnet`, `csharp` and `c#` all name one SDK. The planner's spelling is
    not ours to predict, and a missing alias here costs a false refusal."""
    for lang in ("dotnet", "csharp", "c#"):
        f = _flake(language=lang, verify_commands=["dotnet test"])
        assert _has_attr(f, "dotnet-sdk"), lang
        # The bare `pkgs.dotnet` attr does NOT exist at the pinned rev, and a
        # missing attr fails the whole devShell eval.
        assert not _has_attr(f, "dotnet"), lang
        assert not _has_attr(f, "python313"), lang


def test_node_and_its_spellings_get_the_runtime() -> None:
    for lang in ("node", "nodejs", "javascript", "typescript", "js", "ts"):
        f = _flake(language=lang, verify_commands=["npm test"])
        assert _has_attr(f, "nodejs_22"), lang
        assert not _has_attr(f, "python313"), lang


def test_language_matching_is_case_insensitive() -> None:
    """Same convention as the alias and drop tables. `Rust` is not a different
    language, and a case-sensitive lookup would REFUSE it -- turning a working
    build into a hard provisioning failure."""
    assert _has_attr(_flake(language="Rust"), "cargo")
    assert _has_attr(_flake(language="JavaScript"), "nodejs_22")


# ── what must NOT change ────────────────────────────────────────────────────


def test_an_absent_language_still_gets_the_python_harness() -> None:
    """The `or "python"` default is deliberate and correct. Breaking this would
    trade one silent-wrong-toolchain bug for a much louder one across every
    manifest that omits the field."""
    f = _flake(verify_commands=["pytest -q"])

    assert _has_attr(f, "python313")
    assert 'p."pytest"' in f


def test_an_explicit_python_language_is_unchanged() -> None:
    f = _flake(language="python", verify_commands=["pytest -q"])

    assert _has_attr(f, "python313")
    assert 'p."pytest"' in f


def test_go_keeps_its_version_aware_resolver() -> None:
    """Go is deliberately NOT in the table: its attr is computed from
    `toolchain`, not fixed."""
    assert _has_attr(_flake(language="go"), "go")
    assert _has_attr(_flake(language="go", toolchain={"go": "1.22"}), "go_1_22")


# ── the refusal ─────────────────────────────────────────────────────────────


def test_a_declared_unknown_language_is_refused() -> None:
    """FAIL CLOSED. The alternative -- what this fixes -- is a plausible Python
    shell that cannot run the declared commands."""
    with pytest.raises(ProvisionError) as exc:
        _flake(language="cobol", verify_commands=["cobc -x test.cob"])

    msg = str(exc.value)
    # The error has to name the language AND the fix; a bare "unsupported" sends
    # the reader back into the generator to find out what to do about it.
    assert "cobol" in msg
    assert "_LANG_ATTRS" in msg


def test_the_refusal_does_not_leak_a_python_flake() -> None:
    """Belt and braces: an exception, not a returned string. A caller that
    swallowed the error and used a partial result would be back at #1012."""
    for lang in ("cobol", "fortran", "elixir", "haskell"):
        with pytest.raises(ProvisionError):
            _flake(language=lang)


def test_an_empty_language_string_is_absent_not_unknown() -> None:
    """`""` is falsy, so `(m.language or "python")` treats it as omitted. That
    is the right reading -- an empty field is a missing field, not a claim about
    a language called "" -- and it must not hit the refusal path."""
    assert _has_attr(_flake(language=""), "python313")


# ── the toolchain composes with the lane blocks ─────────────────────────────


def test_a_declared_node_language_does_not_double_the_runtime() -> None:
    """The browser and jest blocks add nodejs_22 themselves. A doubled attr
    still evaluates, but the flake is a committed deliverable."""
    assert _flake(language="typescript", system_packages=["jest"]).count("pkgs.nodejs_22") == 1
    assert _flake(language="node", system_packages=["chromium"]).count("pkgs.nodejs_22") == 1


def test_system_packages_still_ride_along_on_a_declared_language() -> None:
    """The table supplies the toolchain, not the whole shell -- extra tools must
    still reach it, exactly as they do on the go path."""
    f = _flake(language="rust", system_packages=["pkg-config", "openssl"])

    assert _has_attr(f, "rustc")
    assert _has_attr(f, "pkg-config")
    assert _has_attr(f, "openssl")


def test_a_rust_browser_lane_does_not_buy_the_python_web_stack() -> None:
    """The browser clause needs a POSITIVE python signal (the #996/#1001 fix).
    A declared non-python language is not one, and the OOM that clause caused is
    the reason it matters."""
    f = _flake(language="rust", system_packages=["chromium"])

    assert _has_attr(f, "playwright-test")
    assert "fastapi" not in f
    assert not _has_attr(f, "python313")

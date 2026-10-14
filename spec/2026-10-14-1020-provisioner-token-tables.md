---
status: approved
issue: 1020
intent: intent/2026-10-14-1020-provisioner-token-tables.md
---

# Spec: the provisioner's token tables disagree

Approved unseen with the intent (decision 4).

## Design

All changes are in `scripts/nix_provisioner.py` unless stated.

### 1. One lookup for a `system_packages` word

`_system_pkg_attrs(m, lang)` lower-cases every word (decision 2), then takes the
first rule that matches:

1. **`python` / `pip`:** dropped on the Python branch, where the harness
   supplies them. On any other branch they give `python313`, the default
   `_PY_ATTR` (pip ships inside the interpreter).
2. **In `_DROP_SYSTEM_PKGS`:** dropped. (`python` and `pip` leave this table.)
3. **In `_LANG_ATTRS`:** that list. So `rust` gives `rustc` and `cargo` in both
   places, and `java`, `dotnet` and the node words agree too.
4. **In `_SYSTEM_PKG_ALIASES`:** that attribute. `rust` and `dotnet` leave this
   table because rule 3 now covers them. `node`, `npm` and `vitest` stay.
5. **Anything else:** passed through, lower-cased.

The dedupe in `generate_flake` already collapses any overlap.

### 2. A toolchain version the pin does not carry is installed (decision 1)

- **Go.** If `toolchain.go` is not in `_GO_ATTR`, emit the default `pkgs.go`
  plus `GOTOOLCHAIN = "go<ver>"`, where `<ver>` is normalised so that `1.22`
  becomes `1.22.0` and `1.22.3` stays as it is. Go 1.21+ then downloads and
  runs that toolchain on first use.
- **Python.** If `toolchain.python` is not in `_PY_ATTR`, emit `pkgs.uv`
  instead of the Nix interpreter and `withPackages` set, plus a `shellHook`
  that:
  1. runs `uv venv --python <ver> "$PWD/.factory-venv"` (uv downloads the
     interpreter);
  2. runs `uv pip install` for the same library list `_python_libs` gives
     today;
  3. prepends the venv's `bin` to `PATH`.

  The hook runs again on every `nix develop`, and uv's cache makes the repeat
  cheap.
- **In both cases** the flake carries a comment naming the requested version
  and how it is installed, and `generate_flake` logs a warning. The drift is
  visible, not silent.
- A version in the table behaves exactly as today. A missing `toolchain` entry
  still gives the default.

### 3. An evaluation test, gated on Nix (decision 3)

`tests/test_nix_provisioner_attrs_eval.py` builds the set of every attribute
the tables can emit:

- every value in `_LANG_ATTRS`, `_SYSTEM_PKG_ALIASES`, `_PY_ATTR` and `_GO_ATTR`;
- the fixed attributes the generator adds: `nodejs_22`, `playwright-test`,
  `dejavu_fonts`, `uv`, `go` and `python313`.

It runs one `nix eval` that forces each attribute's `drvPath` against
`DEFAULT_NIXPKGS`. Forcing the derivation matters, because evaluating only the
name passes on a lazy list. The test fails and names every attribute that does
not exist. When `nix` is not on PATH, it skips with a reason that says the
attributes were not verified.

## Alternatives rejected

- **Refusing, or falling back on, an unknown version.** Ruled out by decision 1.
- **A second, older nixpkgs input for old toolchains.** That would mean a
  second pin, lock and narHash to maintain, and old pins stop being cached.
  The toolchain managers already solve this.
- **Folding everything into one new table.** That would rewrite tables that
  carry their own provenance comments. A single lookup order over the existing
  tables fixes the disagreement with a smaller diff.

## Risks

- **An installed version is not reproducible the way the Nix pin is.** It
  needs network access when the shell starts, and the patch version varies
  over time. That is the cost of decision 1, and the flake comment states it.
- **Lower-casing everything** breaks a manifest that relies on a mixed-case
  attribute such as `SDL2`. The user accepted this.
- **`python` on non-Python branches** now adds an interpreter where it used to
  vanish silently. That is a fix, but it does change the shell.
- **Vendored copies** in other repos pick this up at their next pin bump.

## Verification

- Unit tests for each rule in section 1:
  - `rust` as a system package gives `cargo`;
  - `python` on rust gives `python313`;
  - `python` on the Python branch is still dropped;
  - `OpenSSL` becomes `openssl`.
- Unit tests for section 2:
  - an unknown Go version emits `GOTOOLCHAIN`;
  - an unknown Python version emits `uv` and the hook, with no `python313` in it;
  - known versions are unchanged.
- The existing provisioner tests and the in-file self-test still pass.
- The evaluation test passes locally, where Nix is present.
- A generated rust-plus-`python` flake and a `python 3.9` flake are evaluated
  and run by hand (`nix develop --command cargo --version`, `python --version`).

---
status: approved
issue: 1020
spec: spec/2026-10-14-1020-provisioner-token-tables.md
---

# Plan: the provisioner's token tables disagree

Approved unseen with the intent. Worktree: `../Factory-1020`. Branch:
`fix/1020-provisioner-token-tables`. File: `scripts/nix_provisioner.py`. Run the
tests with `uvx --with pytest --with pyyaml pytest tests/test_nix_provisioner*.py -q`,
and the in-file self-test with `python3 scripts/nix_provisioner.py` (or however
`_test()` is invoked at the bottom of the file).

## Decisions carried over

1. **A `system_packages` word goes through one lookup**, in this order: lower-case
   it; then `python`/`pip` (dropped on the Python branch, `python313` on any
   other); then `_DROP_SYSTEM_PKGS`; then `_LANG_ATTRS` (a list); then
   `_SYSTEM_PKG_ALIASES`; otherwise pass it through, lower-cased.
   `python` and `pip` leave `_DROP_SYSTEM_PKGS`. `rust` and `dotnet` leave
   `_SYSTEM_PKG_ALIASES`.
2. **An unknown Go version** emits `pkgs.go` plus `GOTOOLCHAIN = "go<X.Y.Z>"`,
   where a bare `X.Y` becomes `X.Y.0`. **An unknown Python version** emits
   `pkgs.uv` plus a `shellHook` that creates `$PWD/.factory-venv` with
   `uv venv --python <ver>`, `uv pip install`s the `_python_libs` list, and
   prepends the venv's `bin` to `PATH`. In both cases the flake gets a comment
   and the generator logs a warning. Known versions are unchanged.
3. **A Nix-gated evaluation test** forces `drvPath` for every attribute the
   tables can emit, against `DEFAULT_NIXPKGS`, and skips loudly without Nix.

## Steps

1. Coder: **Codex**. Decision 1.
   - Change `_system_pkg_attrs` to take the resolved `lang` and apply the lookup
     order. Update the call in `generate_flake`, which must pass `lang`; the
     descriptor branch keeps prepending as it does today.
   - Remove `python` and `pip` from `_DROP_SYSTEM_PKGS`, and `rust` and `dotnet`
     from `_SYSTEM_PKG_ALIASES`. Rewrite the comments on both tables in one or
     two lines each, saying why the entries moved.
   - Add tests to `tests/test_nix_provisioner_language.py`, using the existing
     `_flake` and `_has_attr` helpers:
     - `system_packages: ["rust"]` gives both `rustc` and `cargo`;
     - `language: rust` with `system_packages: ["python", "pip"]` gives `python313`;
     - `language: python` with `system_packages: ["python"]` gives exactly one interpreter line;
     - `["OpenSSL"]` gives `pkgs.openssl`.
   - Check: the provisioner tests and the in-file self-test pass.
   - Traps: `manifest_digest` already lower-cases `system_packages`; leave it
     alone. Do not change `_LANG_ATTRS`.
2. Coder: **agy**. Decision 2.
   - In `_go_attr` and `_python_attr`'s callers in `generate_flake`, detect a
     requested version that is not in the table.
   - Go: keep `pkgs.go` and add an env line `GOTOOLCHAIN = "go<X.Y.Z>";`.
   - Python: replace the Nix interpreter line with `pkgs.uv`, and add a
     `shellHook` to the `mkShell` attribute set. Inside the hook, quote the
     version and package names for the shell, and use the Nix `''` string
     form so `$PWD` survives.
   - Add a comment line inside the flake that names the requested version and
     the installer, and add `logging.getLogger(__name__).warning(...)`.
   - Add tests to `tests/test_nix_provisioner_language.py`:
     - `toolchain: {go: "1.22"}` gives `GOTOOLCHAIN = "go1.22.0"` and `pkgs.go`;
     - `toolchain: {python: "3.9"}` gives `pkgs.uv` and `uv venv --python 3.9`,
       and does not contain `python313`;
     - `{python: "3.12"}` still gives `python312` and no `uv`.
   - Check: the provisioner tests and the self-test pass.
   - Traps:
     - The flake is an f-string, so braces need doubling.
     - `env_lines` already exists for env vars, so reuse it.
     - Do not touch the descriptor branch.
3. The session. Decision 3, plus the live proof.
   - Write `tests/test_nix_provisioner_attrs_eval.py` and run it locally with Nix.
   - Evaluate a rust-plus-`python` flake and a `python 3.9` flake by hand, and
     run `cargo --version` and `python --version` inside them.
   - Then: the Opus review, the PR, and the who-did-what record.

## Tests

| Command | Expected |
|---|---|
| `uvx --with pytest --with pyyaml pytest tests/test_nix_provisioner*.py -q` | passes |
| the in-file self-test | passes |
| `tests/test_nix_provisioner_attrs_eval.py`, with Nix | passes; without Nix it skips with a reason |

## Rollback

Revert the PR. Vendored copies are unaffected until their next pin bump.

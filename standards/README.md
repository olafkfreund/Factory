# Factory shared coding standards

This directory is the **single source of truth** for the fleet's code-quality
bar. See [`coding-standards.md`](./coding-standards.md) for the normative rules.

## Files

| File | What it is |
|---|---|
| `coding-standards.md` | The normative standard (Python, TypeScript, cross-cutting, CI). |
| `ruff.toml` | Shared Python lint baseline. Services `extend` it; tighten-only. |
| `mypy.ini` | Shared `mypy --strict` baseline. Services inherit; tighten-only. |
| `tsconfig.base.json` | Shared TypeScript strictness baseline. Services `extends` it; tighten-only. |
| `.editorconfig` | Copy to each repo root. |

## How services consume it

**Today (until `factory-core` is published - epic Factory#154):** each service
vendors a pinned copy and a CI **drift gate** diffs the copy against this hub at a
pinned SHA, so a service cannot silently fork the baseline. Per-service configs
may only TIGHTEN (a config-lint check enforces this).

**Target:** publish these as part of a versioned `factory-core` / `factory-standards`
package consumed via pinned semver, so the baseline is a dependency, not a copy.

## Tighten-only rule

A service config may add rules or lower numeric caps. It may **not** remove a
selected rule category, raise a complexity cap, or disable a gate. This keeps the
fleet bar monotonic.

---
status: draft
issue: 1020
author: olafkfreund
---

# Intent: the provisioner's token tables disagree

## Problem

`scripts/nix_provisioner.py` turns words in a manifest into nixpkgs attributes.
It uses five tables: `_LANG_ATTRS`, `_SYSTEM_PKG_ALIASES`, `_DROP_SYSTEM_PKGS`,
`_PY_ATTR` and `_GO_ATTR`. The same word can mean different things depending on
which table reads it. Each mismatch below produces a flake that evaluates but
gives the lane the wrong tools:

1. **`rust` means two things.** As a `language` it gives `rustc` and `cargo`.
   As a `system_package` it gives only `rustc`, so `cargo test` fails with
   `cargo: not found` (Fable review, confirmed).
2. **`python` and `pip` are always dropped.** That is correct on the Python
   branch, whose harness provides them. On any other branch,
   `{"language": "rust", "system_packages": ["python"]}` silently gets no
   Python at all.
3. **An unknown toolchain version falls through silently.** Since #1012, an
   unknown `language` is refused. An unknown version is not:
   `toolchain: {python: "3.9"}` quietly gives Python 3.13.
4. **Letter case is handled inconsistently.** Aliased and dropped words are
   lower-cased. Any other word passes through as written, so `OpenSSL` emits
   `pkgs.OpenSSL` and the flake fails to evaluate.

Hub CI has no Nix. The existing tests check the flake *text*, and every comment
saying "measured against the pin" was checked by hand. That is how mismatches
1, 2 and 4 got through review.

## Proposed outcome

- A word gets the same attributes wherever it appears in the manifest, so
  `rust` means `rustc` plus `cargo` in both places.
- `python` or `pip` named on a non-Python branch gives a Python interpreter.
- An unknown toolchain version is handled the same way as an unknown language
  (open question 1).
- Letter case follows one rule (open question 2).
- A test proves every table entry is a real attribute in the pinned nixpkgs
  (open question 3).

## Affected users and systems

- `scripts/nix_provisioner.py`, its tests, and the copies other repos vendor
  from the hub through the drift gates (the `nix_provisioner` vendoring pattern).
  The vendored copies follow a pin bump. They are not part of this change.
- Lanes in TFactory and AIFactory that provision through it. Their behaviour
  changes only for the cases above.

## Constraints

- No change for any manifest that works today. The `language`-absent → Python
  default stays.
- Smallest change: fold the overlap into one lookup. No rewrite of `generate_flake`.

## Open questions

1. **An unknown toolchain version: refuse, or fall back and warn?** The
   `_GO_ATTR` comment chose to fall back on purpose: refusing would break
   manifests that work today on a Go minor the pin no longer carries.
   *Recommend:* fall back, but put the fallback into the generated flake as a
   comment and log a warning, so the drift is no longer silent. Keep refusing
   unknown *languages*.
2. **Letter case.** nixpkgs attributes are case-sensitive, and some real ones
   are mixed case (`SDL2`). *Recommend:* do not lower-case words that pass
   through. Look up aliases and drops without regard to case, and pass anything
   else through as written. Then let question 3's evaluation test catch a
   wrong spelling, instead of guessing.
3. **How to prove the attributes exist.** Hub CI has no Nix. *Recommend:* a
   test that runs `nix eval` on every attribute the tables can produce against
   the pinned nixpkgs. It runs where Nix exists (locally, and in
   `factory-runners`' generated-flake gate) and skips loudly elsewhere. Adding
   Nix to hub CI is a separate decision.

---
status: approved
issue: 3737
intent: intent/2026-11-17-3737-remote-pinning.md
---

# Spec: pin remotes other than origin

## Design

`merge_driver_pins` already lists every config key (`git config -z --includes --name-only
--list`). It now raises `RuntimeError` for any key that starts with `remote.` and ends with
`.uploadpack`, `.receivepack` or `.vcs`, whatever the remote name (names may contain dots).
Callers already fail closed on `RuntimeError`. The existing per-call
`-c remote.origin.*` pins stay: they are harmless and removing them is a separate change.
README and docstring state why a pin is not possible.

## Alternatives rejected

- `-c remote.<name>.uploadpack=...` pins for each listed remote: ineffective (first value wins).
- `--upload-pack=` / `--receive-pack=` on each fetch and push: fixes callers one by one and
  misses `git pull`, `ls-remote` and `clone` of a second remote; blanking `.vcs` makes git look for a `git-remote-` helper instead of disabling helper selection.
- Env `GIT_CONFIG_*` pins: same precedence as `-c`.

## Risks

A repo with a deliberate `remote.<name>.uploadpack` stops working in sandboxed calls until the
key is unset. None is known in the Factory repos.

## Verification

Hub tests: for names `origin`, `evil`, `a.b` and each of the three suffixes the call raises; a
plain remote passes with no pins; a witness test proves git still runs the program despite a
`-c` pin (if git changes, the test says so and the design is revisited). Each service has the
same negative test through its own `core.child_env` wrapper.

---
name: add-a-language
description: Onboard a new programming language to the Factory fleet via a contracts/languages descriptor - write the YAML, prove the lane by running it, land hub-first with the pin-before-registration ordering, and add the negative controls. Use when asked to add or fix language support (build/test lanes, provisioning, detection) for a language the fleet does not yet run.
---

# Add a language to the Factory fleet

One language = one YAML descriptor in the hub, vendored to three consumers.
Before this existed (2026-09-03, Factory#1707), adding a language meant editing
five sites across three repos, one of them vendored; the descriptor collapses
that to a file drop plus a re-vendor. This runbook is the sequence that landed
Swift and Kotlin, including the walls actually hit. Every claim below was run,
not inferred; anything untested says so.

## 0. The one rule that is the point

`available: false` REQUIRES a non-empty `reason`, and the loader refuses the
file without it. This is not bureaucracy: the reason is what turns "this lane
does not run here" into machine-readable RFC-0006 VAL-0 evidence (surfaced by
TFactory `lang_registry.unavailable_lane_reason()` and PFactory
`tfactory_block`'s `unavailable_lanes`) instead of a silent omission that is
indistinguishable from a lane nobody thought about - or worse, a fake pass.
Symmetrically, `available: true` requires the `tool` and the `command` that
actually run, because a lane in a registry that never ran is worth nothing.

## 1. Write the descriptor

Create `contracts/languages/<name>.yaml` in the Factory hub (reachable as
`scripts/languages/<name>.yaml` via symlink; the loader globs the directory
beside itself, so discovery is automatic - no code change). Schema, enforced by
`scripts/language_descriptors.py` (run `python3 scripts/language_descriptors.py`
for its self-tests):

    name: <lowercase, MUST equal the filename stem>
    aliases: [<must include name>, ...]   # unique ACROSS all descriptors
    detect_weight: 1                      # integer >= 1
    proof_command: <tool> --version       # cheap materialize-or-halt probe
    network: none | restricted            # the toolchain's own minimum
    nix:
      packages: [<nixpkgs attrs>]         # eval each against DEFAULT_NIXPKGS first
      shell_env:                          # optional; verbatim Nix string exprs
        VAR: "${pkgs.something}/lib"
    lanes:                                # unit is mandatory (even if false)
      unit:    {available: true, tool: <t>, command: "<cmd>", notes: "..."}
      api:     {available: false, reason: "..."}
      browser: {available: false, reason: "..."}
      integration: {...}
      mutation: {...}
      ui:      {available: false, reason: "..."}   # native-UI honesty slot

Verify every nix attr against the pinned rev BEFORE writing it down, e.g.:

    nix eval --raw 'github:NixOS/nixpkgs/<DEFAULT_NIXPKGS rev>#<attr>.name'

A missing attr fails the WHOLE devShell eval and reads downstream as flakiness
(the Factory#1007/#1009/#1012 defect family). Note that attr versions differ by
nixpkgs rev - two evals on this machine against different revs disagreed on
kotlin (2.4.0 vs 2.4.10) and jdk21 patch level, so eval against the pin in
`nix_provisioner.DEFAULT_NIXPKGS`, not whatever `nixpkgs` flake registry entry
the host has.

## 2. Prove each `available: true` lane by RUNNING it - both directions

Build a minimal project (one function, one or two tests) in a scratch
directory. Generate the flake through the real provisioner, not by hand:

    python3 - <<'EOF'
    import sys; sys.path.insert(0, "scripts")
    from nix_provisioner import generate_flake, generate_lock
    open("/tmp/proj/flake.nix", "w").write(generate_flake(
        {"language": "<name>", "verify_commands": ["<unit command>"]}))
    open("/tmp/proj/flake.lock", "w").write(generate_lock())
    EOF
    nix develop path:/tmp/proj#default --command bash -c "<unit command>"

Then the two mandatory checks:

1. The green direction: the suite passes AND the output shows a non-zero
   executed-test count. Read the COUNT, not the verdict - a Gradle build with
   zero tests collected prints the same "BUILD SUCCESSFUL", and a Swift suite
   with a stale manifest prints "0 failures" while silently running fewer tests.
2. The red direction: mutate the code (or the assertion), rerun, and confirm a
   non-zero exit. A lane that cannot go red proves nothing. Kotlin's mutation
   lane was only marked available after `gradle pitest` generated real mutants
   and killed them (1/1) - presence of a plugin is not proof.

Exit-status trap, hit twice on 2026-09-03: if you pipe the run to `tail` or
`head`, the pipeline reports the LAST stage's status and a hard failure records
as exit 0. Capture `${PIPESTATUS[0]}` (bash) / `$pipestatus[1]` (zsh), or do
not pipe.

If the lane does not work, say so in the descriptor (`available: false` with
the error as the reason, and an upstream issue link) - that is a better
deliverable than a lane that will hang or lie. But distinguish "the obvious
path is broken" from "the capability is unavailable": Swift's `swift test`
looked dead at first contact and turned out to work with one extra convention
(next section). Spend one bounded attempt on the non-obvious path before
settling on false.

## 3. Substrate traps already paid for (do not rediscover)

Swift on Linux, all hit in sequence on 2026-09-03:

- `swift` alone cannot test: the nixpkgs `swift` attr is compiler + driver
  only; `swift test` dies with `exec: swift-test: not found`. SwiftPM is the
  separate `swiftpm` attr. Descriptor carries both.
- swiftpm's manifest-compile helper links corelibs at RUNTIME: without
  Dispatch/Foundation on `LD_LIBRARY_PATH` it dies with `libdispatch.so:
  cannot open shared object file` before Package.swift is even read. This is
  why the schema has `nix.shell_env`.
- nixpkgs swift 5.10 ships NO `libIndexStore.so` anywhere in the store
  (`find /nix/store -name 'libIndexStore.so*'` returns nothing), so swiftpm's
  automatic test discovery fails (NixOS/nixpkgs#379859) and
  `--disable-index-store` does not help. `swift test` WORKS with the pre-5.4
  convention: an explicit `Tests/LinuxMain.swift` + `XCTestManifests.swift`.
- THE trap that convention creates: a test missing from `XCTestManifests.swift`
  silently does not run - `Executed 1 test, with 0 failures`, exit 0, with one
  of two tests absent. Reproduced live. Any generator emitting Swift tests must
  emit the manifest entry alongside every test, and any reviewer must compare
  the executed count against the written test count.

Kotlin / JVM:

- Gradle fetches its Kotlin plugin from plugins.gradle.org and dependencies
  from Maven Central AT BUILD TIME. Proven on the docker-host substrate;
  in-cluster build-Job egress is allowlisted to apk + npm CDNs only, so the
  lane stalls in-cluster until those hosts are allowlisted (Factory#1712).
  Blocked CDNs stall mid-transfer and look like slowness, not a block.
- Use `--no-daemon --console=plain` in Job contexts.

## 4. Land it - this ordering is not negotiable

The loader and descriptors are hub-canonical, vendored byte-exact into
AIFactory (`apps/backend/core/`), TFactory (`apps/backend/tools/runners/`) and
PFactory (`apps/backend/plan/`), policed by
`scripts/check_verification_core_drift.py`. The order, and what breaks when it
is violated:

1. Hub PR: the new `contracts/languages/<name>.yaml` (plus loader/provisioner
   changes if the schema itself grew). Merge it; note the squash-merge SHA on
   main - a PR-branch head SHA dies at merge (Factory#638).
2. One PR per consumer: copy the changed canonical files byte-exact (verify
   with sha256sum against `git show <merge-sha>:<path>`) AND bump
   `HUB_PIN_SHA` in `.github/workflows/verification-core-drift.yml` IN THE
   SAME COMMIT. Copy from the merged commit, not your working tree - a copy
   taken before a late amend vendors stale bytes (this happened; the hash
   check caught it).
   - The pin bump sweeps in EVERY canonical change since the old pin. Diff the
     old pin against the new one for all vendored modules first, and name any
     unrelated change you are consuming in the PR body (TFactory#1271 swept in
     the Factory#1021 job_dispatch fix this way - stated, not silent).
   - Re-vendoring alone ships dead code: check each fork's CALLER actually
     reaches the new path (AIFactory `core/nix_env.py` -> `generate_flake`;
     TFactory `lang_registry` -> descriptor rows; PFactory
     `tfactory_block`/`environment_block`). Running the vendored module's own
     `__main__` self-tests in the consumer checkout proves the sibling import
     and the languages/ discovery work in that package context.
3. Only AFTER all consumer pins are on their default branches: a second hub PR
   registering any NEW files in the drift gate (`CANONICAL_MODULES` +
   `SERVICE_LAYOUTS`). Registration before a consumer carries the file turns
   every PR in that repo red, because the gate's checker floats at hub main
   while each consumer's canonical stays at its pin. For a new language whose
   only change is one more `languages/<name>.yaml`, this step still applies:
   the yaml must be added to `CANONICAL_MODULES` (as `languages/<name>.yaml`)
   and to each consumer's layout.

Consumer repo hygiene that bites: add the vendored loader to each repo's
lint/format exclusions (`ruff.toml` extend-exclude, and TFactory's
`scripts/ratchet_lint.py` VENDORED_SKIP) - the hub formats at width 100 and
holds its own mypy env (types-PyYAML present); a consumer ratchet without the
stubs reports a phantom import-untyped on a file it must not touch anyway.

## 5. Negative controls - a descriptor that is never read must not look like one that is

For each site, unwire the call path (monkeypatch is fine), confirm the test
goes RED, restore. The shipped ones to mirror:

- provisioner: `_resolve_descriptor = None` -> the language's manifest raises
  `ProvisionError` (hub `tests/test_language_descriptors.py`).
- TFactory registry: `_descriptor_registry -> {}` -> `UnsupportedLanguageError`.
- PFactory classifier: descriptor signals removed -> the language's text stops
  classifying as software.
- PFactory environment: descriptor path removed -> loud `ValueError`, never a
  silently mislabelled python/typescript environment (the original bug).
- drift gate: mutate one byte of a vendored yaml -> exit 1.

Also assert the negative DIRECTION of honesty: every unavailable lane
surfaces its reason and carries no command (so nothing can ever report it
passed), and each proven lane's failing mutation exits non-zero.

## 6. Verify like CI, then verify against origin

- Match each repo's PINNED linter versions (read the workflow env, do not
  trust the local venv - both mismatch directions produced wrong answers in
  one day: a bare pinned-mypy env without the project deps invents errors,
  and a stubs-present local env hides ones CI will report).
- TFactory tests run from `apps/backend/.venv`, never the repo root venv
  (the root one silently collects ~1025 fewer tests). Read the COLLECTED
  count.
- After merging, confirm on `origin/<default branch>` per repo: files present,
  pin moved, call sites reading the new path. Local worktrees prove nothing
  about what landed.

## 7. Acceptance test for this document

Onboard the next language purely from this file, with no code edit outside
`contracts/languages/` plus the vendor/pin/registration steps. If any other
edit proves necessary, the descriptor abstraction is incomplete - fix the
abstraction and this file, and treat that as the more valuable finding.
(Not yet performed with a third language; Swift and Kotlin were onboarded
concurrently with building the mechanism itself.)

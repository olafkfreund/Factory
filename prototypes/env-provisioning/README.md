# RFC-0005 prototype — Nix flake env provisioning (spike #62)

Validated on real Nix (2.34.7, NixOS) on 2026-06-15. Proves the recommended
engine for [RFC-0005](../../docs/rfc/0005-environment-manifest-and-toolchain-provisioning.md):
a **Nix flake substrate** that (a) materializes a per-task toolchain and (b)
builds a **daemonless, layered OCI image** for the ephemeral "factory-sandbox".

## Decision: flake (substrate) + devenv (authoring), not devbox

| | control / possibilities | image build | managed services (TFactory api/integration lanes) | verdict |
|---|---|---|---|---|
| **devbox** | low — abstracts Nix away (`devbox.json` = pkg strings) | `generate dockerfile` | awkward | easy mode only |
| **devenv** | high — `devenv.nix`, language presets, **services**, tasks | `devenv container` | first-class | **authoring layer** |
| **raw flake** | max — arbitrary derivations/overlays | **`dockerTools.streamLayeredImage`** (daemonless, layered) | manual | **substrate / image build** |

Use the **flake as the contract substrate** (pins via `flake.lock`, builds the
per-task sandbox image) and **devenv as the ergonomic authoring layer**
(services + tasks). devbox stays an optional easy-mode for trivial repos.

## What this prototype shows

- `nix develop .#{rust,go,python}` → materializes exactly that toolchain
  (Tier A provisioning). The RFC-0005 **evidence gate** is just the proof command,
  e.g. `nix develop .#python -c python3 --version`.
- `nix build .#image-{rust,go,python}` → a **streamable OCI image** containing the
  toolchain, built with no Docker daemon (`dockerTools.streamLayeredImage`).
  Load/run it: `./result | docker load` (or `| podman load`) → launch as the
  per-task ephemeral container via the shared `factory-sandbox` primitive.

## Maps to RFC-0005

- Environment Manifest (contract) → the `toolchains` attr (here) / `flake.nix`
  inputs the planner would generate.
- Per-task ephemeral sandbox (§3.3) → the `streamLayeredImage` output.
- Materialize-or-HALT gate (§3.4) → the `proofs` map.
- TFactory parity → the same flake builds the image that runs the tests; add
  devenv `services` for api/integration lanes.

## Validated locally
```
nix develop .#python -c python3 --version   # Python 3.12.13
nix build .#image-go                          # builds stream-factory-sandbox-go
```

## Next (spike #62)
- devenv.nix variant with a managed Postgres service (TFactory integration lane).
- Benchmark cold/warm build, closure size, cachix push/pull.
- Wire `factory-sandbox` (TFactory `docker_runner.py`) to `./result | <runtime> load` + run.

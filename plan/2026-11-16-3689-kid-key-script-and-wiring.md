---
status: draft
issue: 3689
spec: spec/2026-11-16-3689-kid-key-script-and-wiring.md
coders:   # every file-editing step is done by the lead: small, security-sensitive edits where a handoff costs more than it saves
  all: lead
reviewers:
  - codex   # independent read-only review of the diff (agy is off by owner decision)
---

# Plan: Prepare the 2026Q4 trusted-plan kid key: generation script and optional wiring

Decisions carried over from the approved spec:

- `scripts/gen-trusted-plan-key.sh <KID> <OUT_FILE>` (`--self-test`): kid `[0-9A-Za-z]{2,16}`; refuses to overwrite; writes two lines (`AIFACTORY_TRUSTED_PLAN_KEY_PFACTORY__<KID>`, `PFACTORY_TRUSTED_PLAN_SIGNING_KEY__<KID>`, same value) under `umask 077`; stdout has kid, key names, `sha256(key)[:12]` and a suggested expiry `today+104d`, with a reminder to make `AIFACTORY_TRUSTED_PLAN_EXPIRY` in the aifactory manifest equal to it (the manifest default is `2027-03-15`, right for a key generated on 2026-12-01). The owner applies it explicitly.
- Two Secret keys, not one: the verifier (aifactory) and the signer (pfactory) read different `factory-secrets` keys, so the owner can roll aifactory first and only then enable signing. With one shared key, a pfactory pod restarting early would sign a kid aifactory cannot verify. Both map to the same env name in their own Deployment; PFactory prefers a keyed variable over the legacy one.
- `AIFACTORY_TRUSTED_PLAN_EXPIRY=pfactory/2026q4=2027-03-15` in the aifactory manifest (90 days plus 14 overlap from 2026-12-01; edit the date to the one the script prints for a later generation).
- Retiring the legacy key stays a later PR after the overlap.

## Steps

1. factory-gitops `scripts/gen-trusted-plan-key.sh`: new script with self-test. Check: `--self-test` prints OK.
2. factory-gitops `apps/aifactory/manifests/manifests.yaml` and `apps/pfactory/manifests/manifests.yaml`: optional keyed env (and expiry in aifactory) after the legacy line. Check: `kustomize build` both.
3. factory-gitops `docs/secrets-management.md`: the owner procedure and the inventory row. Check: `python3 scripts/rotation-ledger-check.py --validate-only docs/secrets-management.md`.

## Tests

As above. Owner verification after rolling: a new plan envelope carries `kid: 2026q4`.

## Rollback

Before keyed signing is enabled: revert the commit (unset optional keys leave pods unchanged). After it is enabled, signer first: remove `PFACTORY_TRUSTED_PLAN_SIGNING_KEY__2026Q4` from the Secret, restart `deploy/pfactory`, confirm a new envelope has no `kid`, and only then remove the verifier key and revert. Reverting the verifier first would make pfactory sign a kid aifactory cannot verify.

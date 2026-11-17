---
status: approved
issue: 3689
intent: intent/2026-11-16-3689-kid-key-script-and-wiring.md
---

# Spec: Prepare the 2026Q4 trusted-plan kid key: generation script and optional wiring

## Design

- `scripts/gen-trusted-plan-key.sh <KID> <OUT_FILE>` (`--self-test`): kid `[0-9A-Za-z]{2,16}`; refuses to overwrite; writes two lines (`AIFACTORY_TRUSTED_PLAN_KEY_PFACTORY__<KID>`, `PFACTORY_TRUSTED_PLAN_SIGNING_KEY__<KID>`, same value) under `umask 077`; stdout has kid, key names, `sha256(key)[:12]` and a suggested expiry `today+104d`, with a reminder to make `AIFACTORY_TRUSTED_PLAN_EXPIRY` in the aifactory manifest equal to it (the manifest default is `2027-03-15`, right for a key generated on 2026-12-01). The owner applies it explicitly.
- Two Secret keys, not one: the verifier (aifactory) and the signer (pfactory) read different `factory-secrets` keys, so the owner can roll aifactory first and only then enable signing. With one shared key, a pfactory pod restarting early would sign a kid aifactory cannot verify. Both map to the same env name in their own Deployment; PFactory prefers a keyed variable over the legacy one.
- `AIFACTORY_TRUSTED_PLAN_EXPIRY=pfactory/2026q4=2027-03-15` in the aifactory manifest (90 days plus 14 overlap from 2026-12-01; edit the date to the one the script prints for a later generation).
- Retiring the legacy key stays a later PR after the overlap.

## Alternatives rejected

One shared Secret key (ordering hazard above). Committing the key or an encrypted blob (the repo's agenix path is out of band by design). Setting expiry from a Secret (a date is not secret).

## Risks

If the owner seeds the signer key before rolling aifactory, signing breaks until aifactory is rolled; the doc orders the steps. A stale expiry date in the manifest rejects the key at that date: the doc says to edit it.

## Verification

`scripts/gen-trusted-plan-key.sh --self-test`; `kustomize build` of both apps; the CI manifest-validate; ledger check.

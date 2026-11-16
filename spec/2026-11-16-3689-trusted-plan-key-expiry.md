---
status: approved
issue: 3689
intent: intent/2026-11-16-3689-trusted-plan-key-expiry.md
---

# Spec: trusted-plan key expiry (`not_after`)

## Design

Expiry lives on the verifier, not in the envelope. A new env var
`AIFACTORY_TRUSTED_PLAN_EXPIRY` holds comma-separated `<key>=<date>`
entries. `<key>` is `authority/kid` (keyed) or `authority` (the legacy key);
`<date>` is an ISO date (`2027-02-01`) or an ISO datetime, UTC when no zone is
given. `_select_verification_key` rejects a key whose date has passed:
`key 'pfactory/2026q4' expired <date>`. Time comes from an injectable `now`
(default UTC clock) for tests.

Why the verifier: the envelope is signed by the signer, so a signer-side
expiry would change the signed bytes and need a contract bump; a verifier-side
date is the operator's switch, takes effect without re-signing, and matches the
existing `RETIRED_KIDS` model. The merge gate re-verifies at merge time, so an
expired key also holds the auto-merge of unmerged plans signed with it, the
same as retiring it.

Malformed entries fail closed: an unparseable date makes that key unusable
(reason names the entry, never the secret) rather than silently never expiring.
Unset var: no behaviour change.

The name deliberately avoids the `AIFACTORY_TRUSTED_PLAN_KEY_` prefix: the key
loader treats every variable with that prefix as a verification key, so a
`..._KEY_NOT_AFTER` name would register a key whose secret is a public date
string (Codex review finding, confirmed). A regression test pins this.

Docs: `docs/docs/compliance/trusted-plan-key-rotation.md` gains the expiry
section, the 90-day interval with 14-day overlap, and the owner commands to
introduce `pfactory/<kid>` and retire the legacy key. `environment-reference.md`
gains the new variable.

## Alternatives rejected

- `not_after` inside the signed envelope: changes signed bytes, needs a
  contract version bump and a PFactory release; a signer clock then decides.
- Expiry in PFactory only: the verifier would still accept the old key.
- Moving the live Deployment env now: needs a secret and a live-cluster change.
  That is the owner's step.

## Risks

A date set too early blocks trusted-plan builds (falls back to full planning,
and holds auto-merge of already-signed tasks). Mitigated by the overlap
runbook and the clear reason string. Default off.

## Verification

Unit tests in `tests/test_trusted_plan.py`: expired keyed key rejected; legacy
key rejected; unexpired and unset accepted; malformed date fails closed; the
env parser; the expiry var cannot register a key; a plan verifies before the date and is rejected after it (merge gate re-verifies, so this also holds auto-merge). `pytest tests/test_trusted_plan.py`, ruff.

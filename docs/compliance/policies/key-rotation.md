# Key-Rotation Policy

- **Domain:** Encryption and key management, item "key-rotation policy + automation" (Factory#314)
- **Frameworks:** ISO 27001 A.8.24, SOC 2 CC6.1, PCI DSS 3.7 / 8.3, NIST SC-12 / IA-5
- **Owner:** Security Owner; operated by the platform operator, with a second maintainer reviewing each rotation (four-eyes, as in [R-016](../risk-register.md)).
- **Artifacts:** [intent](https://github.com/olafkfreund/Factory/blob/main/intent/2026-11-16-314-key-rotation-policy.md), [spec](https://github.com/olafkfreund/Factory/blob/main/spec/2026-11-16-314-key-rotation-policy.md), [plan](https://github.com/olafkfreund/Factory/blob/main/plan/2026-11-16-314-key-rotation-policy.md)

## What this adds

Rotation stays **manual** (agenix, accepted control R-016, [runbook](encryption-key-mgmt.md#secret-rotation-runbook-accepted-manual-control-factory315)). The per-credential ledger and the weekly overdue check live in factory-gitops
([`docs/secrets-management.md`](https://github.com/olafkfreund/factory-gitops/blob/main/docs/secrets-management.md)). This page fixes the intervals per class and adds a live
cross-check: the CronJob `secret-rotation-report` (factory-gitops `apps/secret-rotation`) reads one metadata annotation per
Secret, writes the age to the OpenObserve `job_health` stream, and opens one GitHub issue per overdue Secret. It rotates nothing and never reads a value.

## Intervals, owners and procedures

| Class | Examples | Max age | Owner | Procedure |
|---|---|---|---|---|
| API tokens | `GITHUB_TOKEN`, provider API keys, `APP_API_TOKEN`, OIDC client secrets | 90 days (R-016) | Platform operator | [Rotation runbook](https://github.com/olafkfreund/factory-gitops/blob/main/docs/secrets-management.md#rotation-runbook) |
| Keys | `*_JWT_SECRET`, `POSTGRES_PASSWORD` + `factory-db-*`, `minio-creds`, HMAC and signing keys, data-encryption roots | 365 days | Platform operator | Same runbook, per-secret specifics; signing keys use a new kid, never overwrite |
| `factory-secrets` as a Secret | holds both classes above | 90 days (the strictest credential in it decides) | Platform operator | Same |
| Compromise-only | `minio-kms` KEK, `CFACTORY_AUDIT_HMAC_SECRET` | none scheduled | Security Owner | [KEK emergency runbook](https://github.com/olafkfreund/factory-gitops/blob/main/docs/encryption-at-rest.md#kek-compromise-emergency-re-encryption-untested) |
| Claude OAuth | `factory-cli-creds` (Claude key) | about 360 days (`setup-token`) | Platform operator | cred-broker expiry issue, [re-seed](https://github.com/olafkfreund/factory-gitops/blob/main/docs/secrets-management.md#re-seeding-the-claude-oauth-credential) |

Any class rotates immediately on suspected exposure, loss or compromise of an agenix recipient, departure of a holder, or a provider notice.

The report applies 90 days to `factory-secrets` and 365 days to `minio-creds`, `factory-db-{aifactory,pfactory,tfactory}`, `cfactory-api-keys`, `oauth2-proxy-{cfactory,observe,odin}`,
`observe-root`, `odin-ssh-key`, `otel-otlp-auth` and `factory-cli-creds`. The factory-gitops ledger still lists the tokens inside `factory-secrets` at 365 days
against R-016's 90; the stricter accepted control is used here, and aligning the ledger rows is an owner follow-up.

## Recording a rotation

After a rotation, in the same window as the ledger row:

```bash
kubectl --context k3d-factory -n factory annotate secret <name> --overwrite \
  rotation.factory.dev/rotated-at=<YYYY-MM-DD>
```

The date is the **oldest evidenced last-rotated date among all credentials still in that Secret that have a scheduled interval**, from the ledger rows. Compromise-only keys (`CFACTORY_AUDIT_HMAC_SECRET`, which lives in `factory-secrets`) do not count, so a legitimate alert can be cleared without rotating them. It is not necessarily today: rotating the oldest key leaves the
next-oldest as the stamp. Re-stamp after any recreate of the Secret (the `manage-secrets.sh` edit then bootstrap flow, or a manual create), because a recreate drops the annotation.
An unstamped Secret is measured from the policy start, 2026-11-07, so stamping never manufactures a younger credential than the ledger shows.

## Assurance limit

The annotation is an operator-reported date. The report cannot detect a value that changed without a stamp, or drift from the ledger. It makes a missing or stale stamp visible
(`job_health` record with `status` `ok`, `due_soon`, `overdue`, `unstamped`, `missing` or `error`) and raises an issue; it is not independent proof of rotation. Rotation evidence
remains the dated ledger entry and the review record.

## Evidence

- `factory-gitops/apps/secret-rotation/manifests/report.py` and its CI test `test_report.py`.
- `job_health` records `source: secret-rotation`, `kind: secret_rotation`, one per Secret per day.
- GitHub issues labelled `secret-rotation` on this repository.

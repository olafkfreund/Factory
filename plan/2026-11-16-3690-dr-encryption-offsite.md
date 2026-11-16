---
status: approved
issue: 3690
spec: spec/2026-11-16-3690-dr-encryption-offsite.md
coders:
  1: lead (docs; small, no handoff)
  2: lead (shell logic reviewed line by line; codex reviews the diff)
  3: lead
  4: lead
reviewers:
  - codex   # independent read of each draft and the final diff; agy is off by owner decision
---

# Plan: decide R-007, encrypt off-site copies, wire scoped Job S3

Approved decisions carried over from the spec (owner delegation 2026-11-16):

- D1 accept R-007 as AR-003, review by 2027-05-16, "Decided (delegated)",
  signature left to the owner.
- D2 off-site copies are age-encrypted to an owner-supplied public recipient,
  switched on by `OFFSITE_AGE_RECIPIENT` in Secret `offsite-s3-creds`
  (optional key); off by default; ciphertext is not reproducible, so a present
  `.age` key is never re-encrypted or overwritten (header check, plus sidecar
  `.sha256` compare when present).
- D3 destination is the owner's private versioned S3-compatible bucket outside
  the house; nothing is deployed until the owner seeds the Secret and adds the
  directory to the backups kustomization.
- D4 #314 unchanged; offline identity check stays with the owner.
- D5 STS keys are minted by the owner; the aifactory Deployment gets the flag
  false plus optional `S3_STS_*` refs.

Worktrees (under the team scratchpad): `Factory` (branch
`docs/3690-risk-acceptance-dr-encryption`, base main) and `factory-gitops`
(branch `feat/3681-offsite-backup-wiring`, base main).

## Encryption rules (copied from the spec; steps 2 and 3 implement exactly this)

- `OFFSITE_AGE_RECIPIENT` must match `^age1[a-z0-9]+$` else FAIL. Unset or
  empty: the existing plaintext path runs unchanged.
- `fetch-age.sh` (init container): no-op when no recipient; otherwise download
  `https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-amd64.tar.gz`,
  require sha256 `cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10`,
  extract `age/age` (and `age/age-keygen` when `WITH_KEYGEN=1`, tests only) to
  `$SCRATCH/bin`, mode 0555. The script takes `AGE_URL`/`AGE_SHA256` overrides
  only for tests.
- Source dump must pass `gzip -t` on the source stream before encrypting.
- Destination key `<prefix>/<name>.age`. Absent: encrypt to scratch, upload
  (never overwrite), read back, sha256 equal to the local ciphertext else FAIL,
  then upload sidecar `<name>.age.sha256`. Present: do not re-encrypt; FAIL if
  empty or not starting with `age-encryption.org/v1`; if the sidecar exists,
  FAIL on a differing sha256; if it does not, print a warning and pass.
- MinIO: per bucket mirror to scratch, `tar -C` + gzip + age to
  `minio/<bucket>/snapshots/<bucket>-<UTC YYYYMMDD>.tar.gz.age`, same rules.
- Success lines keep the current prefixes (`offsite-copy: OK`,
  `minio-offsite: OK`) so job-watchdog and docs keep working.

## Steps

1. Factory `docs/compliance/risk-register.md`, `statement-of-applicability.md`,
   `r007-ha-options.md`: add AR-003 row and a short AR-003 block (controls with
   file refs, revisit triggers, review 2027-05-16, signature line open); set
   R-007 status to "Accepted (Factory#3690, AR-003)" without changing its
   score; SoA A.8.14 text names the acceptance; r007 header notes
   "decided (delegated), unsigned". Check: `git diff --stat` shows only these
   three files; markdown tables keep their column counts (awk check on `|` counts
   of edited rows).
   Traps: the register's date and score columns must not change.
2. factory-gitops `apps/backups/offsite/`: add `fetch-age.sh`; add the init
   container `fetch-age`, the `OFFSITE_AGE_RECIPIENT` optional env on both
   containers and `fetch-age.sh` to the ConfigMap in `kustomization.yaml`;
   extend `offsite-copy.sh` with the encrypted branch (recipient validation,
   absent/present/sidecar rules); extend `test.sh`. Check:
   `docker run --rm --user 65532 -v $PWD/apps/backups/offsite:/t:ro --entrypoint /bin/sh <pinned mc image> /t/test.sh`
   passes; `kustomize build apps/backups/offsite`.
   Traps: the script is `/bin/sh` (busybox) with `set -euo pipefail`; the root
   filesystem is read-only, so only `/scratch` is writable; the cronjob image
   pin must not change (CI greps it); no secret value is printed.
3. factory-gitops `apps/backups/minio-offsite/`: the same init container and
   env; `minio-offsite.sh` encrypted branch (mirror to scratch, tar, gzip, age,
   absent/present/sidecar rules, read-back hash); `emptyDir.sizeLimit` 5Gi;
   extend `test.sh`. Check: the same docker command for that directory, and
   `kustomize build apps/backups/minio-offsite`.
   Traps: the existing plaintext path and its tests stay byte-for-byte as
   they are when no recipient is set.
4. factory-gitops `apps/aifactory/manifests/manifests.yaml` (the env block next
   to `S3_ACCESS_KEY`/`S3_SECRET_KEY`, about lines 653-656): add
   `AIFACTORY_SCOPED_JOB_S3` = "false" and `S3_STS_ACCESS_KEY`/
   `S3_STS_SECRET_KEY` from `minio-creds` keys `STS_ACCESS_KEY`/`STS_SECRET_KEY`
   with `optional: true`. `docs/secrets-management.md`: add the two optional
   keys to the `minio-creds` row. `docs/restore.md` and
   `docs/encryption-at-rest.md` where it states off-site plaintext: the
   encrypt switch, `age -d -i <identity>` to decrypt, owner enable steps
   (offline key backup first, STS enable order). Check: `kustomize build
   apps/aifactory/manifests | grep -c S3_STS` is 2, `kustomize build` of
   `apps/backups/manifests` is unchanged (diff against origin/main), the repo's
   `manifest-validate` commands pass locally if runnable.
   Traps: Argo CD syncs `main` live; the flag must stay "false".
5. Issues (after the PRs are green): one "Decision (owner delegation
   2026-11-16):" comment on #3690, #3691, #3681, #314 and AIFactory#2023 with
   the owner steps; close #3690 only.

## Tests

Required test cases (a PASS line each), run with the real `age`/`age-keygen`
fetched by `fetch-age.sh`, never a stub:

- postgres: encrypted happy path (decrypt with a throwaway key, content equals
  the source dump); retry for the same dump passes without re-encrypting;
  existing `.age` is not overwritten; bad recipient refused; empty or
  headerless existing object fails; corrupted read-back (hash mismatch) fails;
  sidecar mismatch fails; missing sidecar warns and passes; no recipient keeps
  the plaintext cases unchanged.
- minio: encrypted snapshot decrypts and `tar -x` restores both buckets with
  equal content; same absent/present/sidecar cases; plaintext cases unchanged.
- manifests: rendered CronJobs carry `OFFSITE_AGE_RECIPIENT` (optional) in both
  the init and the copy container (grep count 2 per CronJob).
- CI: `backup-offsite-test.yml` and `backup-drill-test.yml` run the tests with
  `--user 65532` and keep their existing readonly-container checks and the
  kustomize-build greps; edit them in step 2/3 for the user flag only.
- AIFactory: `kustomize build apps/aifactory/manifests` diffed against
  origin/main shows exactly the three new env entries.

- Both `test.sh` files in the pinned mc image as UID 65532 (needs network for
  `fetch-age.sh`); expected: all PASS lines.
- `kustomize build` for `apps/backups/offsite`, `apps/backups/minio-offsite`,
  `apps/aifactory/manifests`, `apps/backups/manifests`.
- `codex review --base origin/<base>` per repo, at most two rounds.

## Rollback

Revert the PRs. Nothing deployed changes: the off-site directories are
unreferenced and the aifactory flag is false.

## Deviations

- Listing errors fail closed (no "prefix may not exist" fallback): S3 lists an
  unused prefix as empty, so the fallback was unneeded and could overwrite.
- Never-overwrite is check-then-copy, not atomic (`mc cp` has no create-only
  mode); documented in factory-gitops `docs/restore.md`, relies on destination
  versioning for hand-started overlapping Jobs.

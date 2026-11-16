---
status: approved
issue: 3690
intent: intent/2026-11-16-3690-dr-encryption-offsite.md
---

# Spec: decide R-007, encrypt off-site copies, wire scoped Job S3

## Decisions (owner delegation 2026-11-16, "use the recommendations")

| # | Decision | Why this option |
|---|---|---|
| D1 | Accept R-007 as AR-003 for six months, review by 2027-05-16, with the compensating controls and revisit triggers already drafted in `docs/compliance/r007-ha-options.md`. Recorded "Decided (delegated)"; the Security Owner's signature stays an owner action. | The recommendation in the #3690 thread and in `r007-ha-options.md` (option A). A second failure domain needs a host or budget only the owner can supply. |
| D2 | Off-site copies are encrypted client-side with age to a recipient (public key) the owner supplies; the private key stays offline. Off unless `OFFSITE_AGE_RECIPIENT` is set. | The recommended default; keeps the destination provider out of the trust boundary. |
| D3 | Destination is the owner's pick: a private, versioned S3-compatible bucket outside the house, EU, about 90 days lifecycle, key that cannot delete. The job needs only the existing `offsite-s3-creds` Secret. | Recorded in the #3681 thread; a provider is a purchase decision. |
| D4 | #314: no change to the decided design (static KEK, no KES). The offline identity check stays an owner action; a decision comment restates the exact command. | Already decided in the #314 thread (2026-11-16 status). |
| D5 | AIFactory#2023: the MinIO hook (`apps/minio/manifests/manifests.yaml`, `minio-create-bucket`) creates the `aifactory-sts` policy and user from `STS_ACCESS_KEY`/`STS_SECRET_KEY` in `minio-creds`. It does not generate them, and in-cluster generation would need a Job with write access to a Secret that lives outside git. So the keys are minted by the owner; the Deployment is wired with the flag false and optional refs. | Least risky: no new Secret-writing component. |

## Design

1. **Risk register (Factory).** Add AR-003 to the Risk-acceptance log, set R-007
   to "Accepted (Factory#3690, AR-003)" with the review date, update SoA
   A.8.14 text, and mark `r007-ha-options.md` as decided-delegated. Do not
   change R-007's score.
2. **Postgres off-site (`apps/backups/offsite`).** When `OFFSITE_AGE_RECIPIENT`
   is set the script: validates it against `^age1[a-z0-9]+$`; checks the newest
   dump is fresh and a valid gzip (`gzip -t` on the source stream); then
   - if `postgres/<dump>.age` is absent at the destination: encrypts with
     `age -r` into scratch, uploads it (never overwrites), reads it back,
     compares sha256 with the local ciphertext, then uploads a sidecar
     `postgres/<dump>.age.sha256`;
   - if it is present (a retry, or a second run for the same dump): does not
     re-encrypt, because age output differs on every run. It requires a
     non-empty object starting with the age header line
     `age-encryption.org/v1`, and compares its sha256 with the sidecar when
     the sidecar exists. Without a sidecar it reports a warning, not a failure,
     so a crash between upload and sidecar cannot wedge later runs.
   It cannot decrypt, so it never hashes plaintext. With no recipient the
   current plaintext mirror path is unchanged.
   Wiring: both CronJobs get `OFFSITE_AGE_RECIPIENT` from `offsite-s3-creds`
   (`optional: true`) on the init container and the copy container; adding the
   public key to that Secret is what switches encryption on. The `age` binary
   comes from an init container running `fetch-age.sh` (shipped in the same
   ConfigMap), which downloads the pinned release (v1.3.2, sha256 pinned) into
   the scratch volume and exits at once when no recipient is set.
3. **MinIO off-site (`apps/backups/minio-offsite`).** With a recipient, each
   bucket is mirrored to scratch, tarred, gzipped and age-encrypted to
   `minio/<bucket>/snapshots/<bucket>-<UTC date>.tar.gz.age`, with the same
   absent/present/sidecar rules, and verified by read-back hash. Snapshots hold
   current object versions only. Scratch grows to 5Gi to match the postgres
   job. Without a recipient the existing per-object mirror and diff are
   unchanged.
4. **Wiring for AIFactory#2023 (factory-gitops `apps/aifactory`).** Add
   `AIFACTORY_SCOPED_JOB_S3: "false"` and `S3_STS_ACCESS_KEY`/`S3_STS_SECRET_KEY`
   from `minio-creds` keys `STS_ACCESS_KEY`/`STS_SECRET_KEY` with
   `optional: true`. Enabling later is one Secret edit plus flipping the flag.
   Document the two keys in `docs/secrets-management.md`. Enable order for the
   owner: add the keys to `minio-creds`, resync the minio Argo app so the
   PostSync hook reruns and confirm its log says `aifactory-sts user ready`,
   then restart aifactory with the flag true, then run one build and one spec
   Job.
5. **Docs (factory-gitops).** `docs/restore.md` gets the encrypt switch, how to
   decrypt (`age -d -i <identity>`), and the owner enable steps.
6. **Issue comments.** One "Decision (owner delegation 2026-11-16):" comment per
   issue with the owner steps. Close only #3690 (decision recorded, AR-003
   entered); #3681, #3691, #314 and AIFactory#2023 stay open for owner steps.

## Alternatives rejected

- **Provider-side encryption only.** Trusts the destination; rejected by D2.
- **Encrypt with `openssl`/GPG.** Not in the mc image; age is a single static
  binary and the owner's recommendation.
- **Build a custom image with age.** New image to build, scan and pin: more
  machinery than a hash-pinned download in an init container.
- **Generate STS keys in-cluster.** Needs write access to a Secret that is
  seeded out of band; widens blast radius for little gain (D5).
- **HA Postgres (CloudNativePG) on the one host.** Does not remove the host
  failure R-007 describes (`r007-ha-options.md`, option C).
- **Suspended CronJob placeholders.** job-watchdog raises critical on a
  suspended, never-run CronJob (existing note in `offsite/cronjob.yaml`).

## Risks

- The init container needs egress to github.com when a recipient is set; if
  blocked, the job fails visibly (job-watchdog) and nothing is uploaded.
- A lost private key makes every encrypted copy unrecoverable: the owner must
  back it up offline before enabling (an owner action in the docs).
- Daily full MinIO snapshots multiply destination storage; the recommended
  90-day lifecycle bounds it. Snapshots omit noncurrent versions.
- Nothing is deployed: the new init container and env only reach a cluster when
  the owner adds `../offsite`/`../minio-offsite` to the backups kustomization.
- The aifactory edit is synced by Argo CD; a missing optional Secret key is
  tolerated and the flag is false, so behaviour is unchanged.

## Verification

- `apps/backups/offsite/test.sh` and `minio-offsite/test.sh` run in the pinned
  mc image as UID 65532 (CI: `backup-offsite-test.yml`, `backup-drill-test.yml`).
  The new cases run `fetch-age.sh` for real (downloaded binary, permissions,
  checksum) and use real `age`/`age-keygen` with a throwaway key: encrypt,
  decrypt and compare content, including tar extraction for MinIO. Further
  cases: bad recipient refused, existing `.age` not overwritten, a retry after a
  successful upload passes, corrupted read-back fails, truncated existing object
  (no age header) fails.
- `kustomize build` of both off-site directories and `apps/aifactory`; the
  rendered CronJobs carry `OFFSITE_AGE_RECIPIENT` in both containers.
- Argo diff of `apps/aifactory` shows only the three new env entries.

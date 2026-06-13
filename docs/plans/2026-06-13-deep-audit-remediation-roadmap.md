# Deep-audit remediation roadmap (June 2026)

Tracking doc for the remediation epic spun out of the June-2026 deep audit
(a 16-agent review of all four services plus this meta-repo, cross-checked
against the 2026 landscape). It complements Factory#42 (proof / verify / sell):
where #42 covers proving and selling the pipeline, this epic covers the
security-hardening, CI-gate and code-quality work #42 under-tracks.

Epic: olafkfreund/Factory#45.

## Audit verdict

The contract spine is real and verified end-to-end. A governed plan flows
PFactory -> AIFactory -> TFactory -> CFactory, signed as an RFC-0002 Task
Contract v2, executed on the trusted-plan fast path, tested against the declared
acceptance criteria on the real build, and surfaced on a single cockpit. That
spine is the hard part, and it works.

Where the program is behind is proof-at-scale and the sandbox:

- Proof-at-scale: the seam regression that catches cross-service boundary bugs
  runs only nightly in this meta-repo. A contract-breaking change can merge into
  a service repo and go live before the next night catches it. The gate needs to
  run at PR and deploy time in each service.
- The sandbox: the agent command allowlist is a regex that a shell can bypass
  (command substitution, pipes). The enforced control behind it -- a real OS
  sandbox -- is the single biggest credibility blocker for a skeptical reviewer.

The remainder is trust-hardening (CI security, auth/CORS/SSRF guards) and paying
down god-file debt -- real, but not spine-threatening.

## Remediation epic and child issues

Grouped by repo. Issues marked "PR this session" ship as a branch + PR with
auto-merge on green CI; issues marked "tracked" are larger or design-sensitive.

### Factory (meta-repo)

- olafkfreund/Factory#43 -- docs: fix stale port map + document the trusted-plan
  seam in the OpenAPI spec (PR this session)
- olafkfreund/Factory#44 -- ci: make the PARR seam regression a reusable
  pre-merge / post-deploy gate (PR this session)

### AIFactory (build / Act)

- olafkfreund/AIFactory#553 -- security(ci): fix GitHub Actions script injection
  and harden the copilot PR-review workflow (PR this session)
- olafkfreund/AIFactory#554 -- ci: gate the frontend vitest tests, add
  type-checking, broaden CI triggers (PR this session)
- olafkfreund/AIFactory#555 -- security: retire legacy wildcard API_TOKEN, move
  the WS-terminal token to a header, add a CORS guard (tracked)
- olafkfreund/AIFactory#556 -- refactor: split the routes/tasks.py and
  agent_service.py god-files (tracked)
- olafkfreund/AIFactory#363 -- real OS sandbox for agents: the enforced control
  behind the bypassable allowlist (already tracked; the credibility blocker)

### PFactory (plan + govern / Prepare)

- olafkfreund/PFactory#127 -- security(ci): harden copilot-plan-review.yml
  ([bot]-suffix trust and --allow-all-tools) and fix script-injection sinks
  (PR this session)
- olafkfreund/PFactory#128 -- security: fail-closed the /mcp endpoint, add a CORS
  guard, refuse DISABLE_AUTH startup on non-loopback (PR this session)
- olafkfreund/PFactory#129 -- security: replace the regex command allowlist with
  a shell-AST parser to close the $()/pipe bypass (tracked)
- olafkfreund/PFactory#130 -- chore: finish the Magestic AI -> PFactory rebrand,
  prune inherited skeleton routers, split tasks.py (tracked)

### TFactory (verify / Reflect)

- olafkfreund/TFactory#358 -- security(ci): fix tfactory-dispatch.yml script
  injection and add a DISABLE_AUTH non-loopback startup guard (PR this session)
- olafkfreund/TFactory#359 -- security: SSRF guard for the network-enabled test
  lanes (block link-local / metadata ranges) (PR this session)
- olafkfreund/TFactory#360 -- refactor: split routes/tasks.py and extract a
  shared completion-envelope constants module (tracked)

### CFactory (cockpit / Review)

- olafkfreund/CFactory#81 -- ci+security: add a test workflow gating deploy and
  refuse the default audit HMAC secret outside local mode (PR this session)

## Sequencing -- four waves

The principle is highest-leverage-first: fix the things a skeptical reviewer
latches onto, then make the boundary gate real, then close the sandbox
credibility blocker, then pay down debt.

### Wave 1 (days) -- security CI fixes plus the CFactory test gate

The fastest, highest-leverage work. Fix the GitHub Actions script-injection and
copilot-workflow trust issues across the service repos (AIFactory#553,
PFactory#127, TFactory#358) and stand up the CFactory test workflow that gates
deploy (CFactory#81). These are small, safe, and remove the most obvious
attack surface.

### Wave 2 -- seam-regression-as-gate plus SSRF/auth guards plus docs

Make the cross-service seam regression a reusable pre-merge / post-deploy gate
(Factory#44) and adopt it in each service's deploy. Add the runtime guards:
SSRF for TFactory test lanes (TFactory#359), CORS / fail-closed /mcp /
DISABLE_AUTH startup refusal for PFactory (PFactory#128), and the AIFactory
token/CORS hardening (AIFactory#555). Land the documentation fixes (Factory#43)
so the public spec and roadmap stop undercutting the rest.

### Wave 3 -- the command-allowlist AST parser plus the OS sandbox

The credibility blocker. Replace the regex command allowlist with a shell-AST
parser that closes the command-substitution / pipe bypass (PFactory#129), and
build the enforced OS sandbox behind it (AIFactory#363). Until this lands, the
"agents can't run arbitrary commands" claim is not defensible; once it does, it
is the strongest trust story in the suite.

### Wave 4 (opportunistic) -- god-file refactors plus rebrand/cleanup

Pay down the structural debt as capacity allows: split the routes/tasks.py and
agent_service.py god-files (AIFactory#556, TFactory#360), and finish the
Magestic AI -> PFactory rebrand and skeleton-router pruning (PFactory#130).
None of this is spine-threatening; it is hygiene that makes the next year of
work cheaper.

---

Complements Factory#42 (proof / verify / sell). Live status lives on the
[Factory Program board](https://github.com/users/olafkfreund/projects/1) and in
epic olafkfreund/Factory#45.

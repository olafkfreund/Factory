#!/usr/bin/env bash
# Branch-protection-as-code for the Factory fleet (Factory#316, Factory#468).
#
# Declares the intended protection for every repo AND every protected branch in
# the program, and can either CHECK the live configuration against that intent
# or APPLY the intent.
#
# CHECK IS THE DEFAULT. With no arguments this script reads live protection,
# diffs it against the declared intent, prints every divergence and exits
# non-zero. It writes nothing. Applying requires an explicit --apply, because a
# tool whose default action is "silently overwrite production config" is the
# wrong shape for something CONTRIBUTING.md tells a stranger to run after a
# fresh clone (Factory#468: three per-repo copies of an "idempotent" apply-only
# script had drifted from live and would have reverted a deliberate decision).
#
# WHY classic protection (not a ruleset): the deploy automation pushes DIRECTLY
# to factory-gitops main (github-actions[bot] via the GITOPS_PAT). With
# enforce_admins=false an admin-owned token bypasses the PR/review requirement,
# so the CD bump keeps working without a bespoke bypass-actor list. The five
# code repos have NO direct-to-main automation (the app commits to feature
# branches; deploy.yml writes to factory-gitops; release.yml pushes tags only),
# so requiring PRs there does not break any bot. See
# docs/compliance/branch-protection.md for the full rationale and rollout order.
#
# Usage:
#   scripts/apply_branch_protection.sh                 # CHECK all repos (default)
#   scripts/apply_branch_protection.sh --repo CFactory # CHECK one repo
#   scripts/apply_branch_protection.sh --plan          # print intended payloads only
#   scripts/apply_branch_protection.sh --apply --repo CFactory   # APPLY one repo
#   scripts/apply_branch_protection.sh --apply         # APPLY all repos
#   WITH_VERIFY=1 scripts/apply_branch_protection.sh --repo AIFactory
#                                                      # include TFactory verify check
#   scripts/apply_branch_protection.sh --signatures --repo CFactory
#                                                      # dry-run: what require-signed-commits WOULD do
#   scripts/apply_branch_protection.sh --signatures --apply --repo CFactory
#                                                      # ENABLE required_signatures on one repo
#
# SIGNED COMMITS (--signatures): OPT-IN and separate from the baseline protection
# above, because turning it on breaks any identity that pushes UNSIGNED commits to
# the protected branch. Every pusher (humans AND automation) must have commit
# signing configured FIRST or their next push is rejected. See the per-repo signer
# checklist printed in dry-run and docs/compliance/signed-commits-and-sod.md for the
# rollout order (humans first, bots signing configured, gitops LAST).
#
# --signatures is ORTHOGONAL to MODE, not a mode of its own: it selects WHICH
# object is acted on (required_signatures, never the protection object), while
# --apply still selects whether anything is written. So --signatures alone is a
# dry-run and --signatures --apply enforces.
#
# Exit codes (check mode): 0 = live matches intent, 1 = divergence found,
# 2 = could not determine (missing tool, missing branch, token without admin).
# A check that cannot read what it compares against FAILS - it never reports
# green (standards/coding-standards.md rule 4.7).
#
# Requires: gh (authenticated with ADMIN on the repos - reading branch
# protection is an admin-only endpoint) and jq.
set -euo pipefail

OWNER="olafkfreund"
MODE="check"                      # check | apply | plan | emit | normalise-stdin
ONLY_REPO=""
EMIT_BRANCH=""
SIGNATURES=0                      # 1 = act on required_signatures (opt-in; see --signatures)
WITH_VERIFY="${WITH_VERIFY:-0}"   # 1 = also require the TFactory verification status (see docs, phase 3)

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) MODE="apply" ;;
    --check) MODE="check" ;;
    --plan|--dry-run) MODE="plan" ;;
    --signatures) SIGNATURES=1 ;;
    --repo) ONLY_REPO="${2:-}"; shift ;;
    # Introspection hooks, no network. --emit prints the NORMALISED intent for one
    # repo/branch; --normalise-stdin prints the normal form of a protection JSON
    # read from stdin. Together they let the comparator be tested offline: the two
    # must agree for a live response that matches intent, and disagree when one
    # field is changed (tests/test_branch_protection_intent.py, rule 4.9).
    --emit) MODE="emit"; ONLY_REPO="${2:-}"; EMIT_BRANCH="${3:-}"; shift 2 ;;
    --normalise-stdin) MODE="normalise-stdin" ;;
    # Same idea for the CODEOWNERS verdict: prints the verdict for a
    # /codeowners/errors payload read from stdin, so both directions are testable
    # without a token (tests/test_branch_protection_intent.py, rule 4.9).
    --codeowners-stdin) MODE="codeowners-stdin" ;;
    -h|--help) sed -n '2,56p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

command -v gh >/dev/null || { echo "gh not found" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 2; }

# The TFactory verification status context (posted by copilot-pr-test.yml /
# pr-review-tests.yml). Only make it a REQUIRED check once you have confirmed it
# posts on EVERY pull request for that repo - otherwise it blocks PRs that never
# got a TFactory run. Off by default; enable with WITH_VERIFY=1.
VERIFY_CTX="tfactory/suite"

# Per-repo intended protection. Fields:
#   CHECKS         : required status-check contexts (job display NAMES as they
#                    appear on the PR, not the workflow job ids)
#   REVIEWS        : 1 = require a PR with >=1 approving review on main; 0 = none
#   CODE_OWNER     : 1 = require_code_owner_reviews (only where CODEOWNERS exists)
#   ENFORCE_ADMINS : 0 = admins (and admin-owned automation tokens) bypass
#   VERIFY         : 1 = eligible to also require $VERIFY_CTX when WITH_VERIFY=1
#   BRANCHES       : every branch that MUST be protected in this repo. A declared
#                    branch that does not exist is an error, not a skip.
#   DEFAULT_BRANCH : the repo's default branch. NOT cosmetic - see Factory#467.
#
# enforce_admins is 0 across the baseline so the factory's own auto-merge loop
# (admin token running `gh pr merge`) and the gitops CD bot keep working.
#
# CHECKS are per-repo because the repos' CI job names genuinely differ (CFactory
# names them "Backend pytest"/"Frontend typecheck + build"; the Python services
# use "backend (ruff + pytest)"). This table is the single place they are
# declared - the previous per-repo copies of this script each hardcoded one
# repo's names and were vendored into repos whose jobs are named differently.
#
# $VCORE_CTX is the exception: all four consumers name that job identically, and
# it is spelled once here so a rename cannot be half-applied. Its workflow header
# has called it a "Blocking drift gate" since Factory#158 while it was required
# nowhere, so a byte mismatch painted one red X on a mergeable PR - prose
# asserting an invariant nothing enforced (Factory#543).
#
# Requiring it was UNSAFE until Factory#525: the gate filtered its pull_request
# trigger by paths, so it did not post at all on a PR touching none of the
# vendored copies, and a required check that never posts blocks the PR forever
# (the same warning $VERIFY_CTX carries above). That filter is gone in all four
# repos, the trigger is now `pull_request: branches: [dev, main]` unfiltered, and
# it was OBSERVED posting on a PR whose whole diff was an unmapped path
# (CFactory#298). Order mattered; this is the second half.
VCORE_CTX="vendored copies match the hub canonical (byte-exact)"

# The PR-diff secret scan, required fleet-wide as of Factory#814. Not one
# repository required any security gate; the scans ran and advised. #805 records
# what that is worth here, and factory-gitops#209 is the worked example -- a
# secret scan red on every PR for two months while two live API keys sat in a
# PUBLIC repo, because a permanently-red optional check is one everybody learns
# to scroll past.
#
# Measured before promoting, last 20 runs each: 20/20 in all five repos. A gate
# too flaky to require is either worth fixing or worth deleting.
#
# THE PR-DIFF JOB ONLY, and the distinction is load-bearing. Each repo's
# secret-scan.yml also has a full-history job gated
# `if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'`,
# so it NEVER runs on a pull request -- it reports `skipping`, verified on live
# PRs in PFactory, TFactory and AIFactory. Requiring that one would block every
# PR in the fleet forever, the exact hazard $VERIFY_CTX and $VCORE_CTX both
# carry warnings about above.
#
# Spelled per repo because the display names genuinely differ: PFactory
# capitalises it, the other three do not, and the hub's single job is just
# "gitleaks". A context that does not match the posted name is indistinguishable
# from a check that never posts.
#
# No `paths:` filter on any of the five, checked before requiring: the trigger
# is a bare `pull_request`, so this cannot leave a PR waiting on a job that
# never runs.
SECRET_CTX_PF="Gitleaks (PR diff)"
SECRET_CTX="gitleaks (PR diff)"
SECRET_CTX_HUB="gitleaks"


repo_config() {
  # Reset the per-branch override FIRST. These are globals set by a case arm,
  # and only one repo sets CHECKS_DEV -- without this it would leak from
  # AIFactory to whichever repo the loop visits next and apply AIFactory's job
  # names to it, which is the same class of bug as #691 pointing the other way.
  CHECKS_DEV=""
  case "$1" in
    CFactory)      CHECKS='["Backend pytest","Frontend typecheck + build","'"$VCORE_CTX"'","'"$SECRET_CTX"'"]'; REVIEWS=0; CODE_OWNER=0; ENFORCE_ADMINS=0; VERIFY=0; BRANCHES="main dev"; DEFAULT_BRANCH="dev" ;;
    Factory)       CHECKS='["ruff + mypy ratchet (diff-scoped, blocking)","ruff format --check (scripts + tests, blocking)","hub test suite + generated package self-test (pytest)","'"$SECRET_CTX_HUB"'"]'; REVIEWS=0; CODE_OWNER=0; ENFORCE_ADMINS=0; VERIFY=0; BRANCHES="main"; DEFAULT_BRANCH="main" ;;
    # PFactory's dev carries `docker (P0 acceptance)` and main does not.
    # PFactory#586 shipped a container that could not start: the gate caught it
    # on the causing PR (red at 12:53Z and 13:01Z on that PR's own branch) and
    # the PR merged anyway, because the check was advisory. Made required on dev
    # in PFactory#588. main does not run the job on every push, so a per-branch
    # override rather than a single CHECKS -- the same shape AIFactory uses
    # below, and for the same reason (#691): one CHECKS would PUT main's set
    # over dev and strip it again.
    PFactory)      CHECKS='["backend (ruff + pytest)","critical (fast PR gate)","'"$VCORE_CTX"'","'"$SECRET_CTX_PF"'"]'; CHECKS_DEV='["backend (ruff + pytest)","critical (fast PR gate)","'"$VCORE_CTX"'","docker (P0 acceptance)","'"$SECRET_CTX_PF"'"]'; REVIEWS=0; CODE_OWNER=1; ENFORCE_ADMINS=0; VERIFY=0; BRANCHES="main dev"; DEFAULT_BRANCH="dev" ;;
    TFactory)      CHECKS='["backend (ruff + pytest)","critical (fast PR gate)","'"$VCORE_CTX"'","'"$SECRET_CTX"'"]'; REVIEWS=0; CODE_OWNER=1; ENFORCE_ADMINS=0; VERIFY=1; BRANCHES="main dev"; DEFAULT_BRANCH="dev" ;;
    # AIFactory's dev is its DEFAULT branch and carries three gates main does
    # not: the ratchet, the format check and the shared-baseline drift gate.
    # A single per-repo CHECKS could not express that, so `--apply` would have
    # PUT the two-check main set over dev and stripped all three (#691).
    # CHECKS_DEV is the per-branch override; unset means "same as CHECKS".
    AIFactory)     CHECKS='["backend (ruff + pytest)","'"$VCORE_CTX"'","'"$SECRET_CTX"'"]'; CHECKS_DEV='["backend (ruff + pytest)","'"$VCORE_CTX"'","ratchet (ruff + mypy on changed Python)","ruff format --check (every Python directory)","shared-baseline drift gate (blocking)","'"$SECRET_CTX"'"]'; REVIEWS=0; CODE_OWNER=1; ENFORCE_ADMINS=0; VERIFY=1; BRANCHES="main dev"; DEFAULT_BRANCH="dev" ;;
    # gitops is bot-driven CD. Its manifests reach the live cluster through
    # ArgoCD, so until factory-gitops#95 it was the least gated repo in the
    # fleet with the highest blast radius; `kustomize build + schema` now runs
    # on every PR. Force-push and deletion stay blocked so ArgoCD's committed
    # history cannot be rewritten or dropped.
    #
    # The secret scan is required as of factory-gitops#209. It had been running
    # and failing on every PR for two months while two live API keys sat in a
    # PUBLIC repo, because it was not required and a permanently-red optional
    # check is one everybody learns to scroll past. Both jobs live in
    # manifest-validate.yml, which carries no `paths:` filter, so requiring this
    # cannot leave a manifest-free PR waiting on a check that never runs.
    factory-gitops) CHECKS='["kustomize build + schema","no literal secrets in manifests"]'; REVIEWS=0; CODE_OWNER=0; ENFORCE_ADMINS=0; VERIFY=0; BRANCHES="main"; DEFAULT_BRANCH="main" ;;
    *) echo "no config for repo: $1" >&2; return 1 ;;
  esac
}

ALL_REPOS=(CFactory Factory PFactory TFactory AIFactory factory-gitops)

# Identities that must have commit signing configured BEFORE required_signatures is
# enabled on each repo's main. Enabling it rejects the next UNSIGNED push from any of
# these, so this is the pre-flight checklist. Human committers are assumed to have set
# up their own signing (see the doc); listed here are the AUTOMATION identities that
# push to (or merge into) main and would otherwise break.
signers_note() {
  case "$1" in
    CFactory|PFactory|TFactory|AIFactory)
      echo "PARR auto-merge bot (admin token running 'gh pr merge' - merge commits must be signed; enable branch 'Require signed commits' AND ensure the merge is a GitHub-signed merge/squash, which GitHub signs server-side)" ;;
    Factory)
      echo "Human committers only (no direct-to-main automation). Confirm every maintainer has verified signing before enabling." ;;
    factory-gitops)
      echo "CRITICAL: github-actions[bot] CD bump (GITOPS_PAT) pushes UNSIGNED commits. Enable ONLY after the CD job signs its commits (import a bot GPG/SSH signing key into the workflow and set git user.signingkey + commit.gpgsign=true, OR switch the bump to the GitHub Contents API which server-signs). Enabling before that FREEZES all deploys." ;;
    *) echo "no signer pre-flight declared for repo: $1" >&2; return 1 ;;
  esac
}

signatures_one() {
  local repo="$1" note
  echo "-------------------- ${OWNER}/${repo} : main : required_signatures --------------------"
  # Capture rather than interpolate. `signer pre-flight: $(signers_note ...)` sent
  # the unknown-repo message to STDOUT, so an unrecognised repo printed
  # "signer pre-flight: unknown repo: X" and carried on as though a pre-flight
  # existed - the absence of a checklist rendered as a checklist. An unknown repo
  # is now a hard error: nothing is written and the caller exits non-zero.
  if ! note="$(signers_note "$repo")"; then
    echo "  ERROR: refusing to act on a repo with no declared signer pre-flight." >&2
    return 2
  fi
  echo "signer pre-flight: $note"
  echo "endpoint: POST repos/${OWNER}/${repo}/branches/main/protection/required_signatures"
  echo "prereq: branch protection must already exist on main (run this script without --signatures first)."
  if [ "$MODE" = "apply" ]; then
    echo ">> enabling required signed commits..."
    gh api -X POST \
      -H "Accept: application/vnd.github+json" \
      "repos/${OWNER}/${repo}/branches/main/protection/required_signatures" >/dev/null
    echo ">> enabled. Unsigned pushes to main are now rejected."
  else
    echo "(dry-run: nothing written. Re-run with --signatures --apply to enforce. Disable later with:"
    echo "  gh api -X DELETE repos/${OWNER}/${repo}/branches/main/protection/required_signatures )"
  fi
  echo
}

# Per-branch intent. `main` is the release branch: up-to-date-required, reviewed,
# conversations resolved. `dev` is the integration branch: the same CI checks
# gate every merge, there is still no review requirement and no
# conversation-resolution gate - a solo maintainer and the factory's own agents
# have nobody to approve their PRs, so requiring review would stall the branch
# (Factory#455 / Factory#468, still current).
#
# `strict` on dev REVERSES the earlier decision, deliberately (Factory#834).
#
# WHY: two PRs whose diffs do not overlap can each be correctly green and still
# break the branch together. #1121 deleted a module and repointed the call sites
# on its branch; #1125 was concurrent, merged first, and carried an import of
# that module forward. Neither conflicted, both read CLEAN, and no CI run ever
# evaluated the combination. TFactory dev was broken for about an hour. The same
# shape recurred twice more the same day and was caught only by checking the
# merge result by hand.
#
# WHAT IT COSTS, measured rather than estimated: 68 PRs merged to dev across the
# four service repos on 2026-08-19. Under `strict` each must be up to date at
# merge time, so a busy day pays a rebase-and-rerun per merge, against a slowest
# job of ~7 minutes. That cost is accepted; the earlier decision weighed the same
# trade without the incident data.
#
# Reverting is a one-line change here plus an --apply.
build_payload() {
  local repo="$1" branch="$2"
  repo_config "$repo"

  local checks="$CHECKS" strict reviews convres
  case "$branch" in
    main) strict=true;  reviews="$REVIEWS"; convres=true ;;
    dev)  strict=true;  reviews=0;          convres=false
          # Per-branch checks (#691): dev may be gated MORE than main, and is
          # for AIFactory, where dev is the default branch.
          [ -n "${CHECKS_DEV:-}" ] && checks="$CHECKS_DEV" ;;
    *) echo "no branch intent for ${repo}@${branch}" >&2; return 1 ;;
  esac

  if [ "$WITH_VERIFY" = "1" ] && [ "$VERIFY" = "1" ] && [ "$branch" = "main" ]; then
    checks="$(jq -c --arg c "$VERIFY_CTX" '. + [$c]' <<<"$checks")"
  fi

  # required_status_checks: null when there are no checks (gitops)
  local rsc="null"
  if [ "$(jq 'length' <<<"$checks")" -gt 0 ]; then
    rsc="$(jq -cn --argjson ctx "$checks" --argjson s "$strict" '{strict: $s, contexts: $ctx}')"
  fi

  # required_pull_request_reviews: null when reviews not required (dev, gitops)
  local rpr="null"
  if [ "$reviews" = "1" ]; then
    rpr="$(jq -cn --argjson co "$CODE_OWNER" \
      '{required_approving_review_count: 1, require_code_owner_reviews: ($co==1), dismiss_stale_reviews: true}')"
  fi

  jq -cn \
    --argjson rsc "$rsc" \
    --argjson rpr "$rpr" \
    --argjson ea "$ENFORCE_ADMINS" \
    --argjson cr "$convres" \
    '{
      required_status_checks: $rsc,
      enforce_admins: ($ea==1),
      required_pull_request_reviews: $rpr,
      restrictions: null,
      allow_force_pushes: false,
      allow_deletions: false,
      required_linear_history: false,
      required_conversation_resolution: $cr
    }'
}

# Reduce an intent payload and a live GET-protection response to the SAME shape
# so a diff between them is meaningful. The live API wraps booleans as
# {"enabled": bool}, returns the check list as either .contexts or .checks[].context,
# and omits .restrictions entirely when unset; the intent payload uses bare
# booleans. Only fields the intent actually declares are compared - anything
# GitHub adds that we do not set (lock_branch, required_signatures, ...) is out
# of scope by construction rather than by accident.
normalise() {
  jq -S '
    def onoff: if type == "object" then (.enabled // false) else (. // false) end;
    {
      required_status_checks:
        (if (.required_status_checks // null) == null then null
         else {
           strict: (.required_status_checks.strict // false),
           contexts: (((.required_status_checks.contexts
                        // ((.required_status_checks.checks // []) | map(.context)))) | sort)
         } end),
      enforce_admins: (.enforce_admins | onoff),
      required_pull_request_reviews:
        (if (.required_pull_request_reviews // null) == null then null
         else {
           required_approving_review_count: (.required_pull_request_reviews.required_approving_review_count // 0),
           require_code_owner_reviews: (.required_pull_request_reviews.require_code_owner_reviews // false),
           dismiss_stale_reviews: (.required_pull_request_reviews.dismiss_stale_reviews // false)
         } end),
      restrictions: (if (.restrictions // null) == null then null else "SET" end),
      allow_force_pushes: (.allow_force_pushes | onoff),
      allow_deletions: (.allow_deletions | onoff),
      required_linear_history: (.required_linear_history | onoff),
      required_conversation_resolution: (.required_conversation_resolution | onoff)
    }'
}

# Does a CODEOWNERS file actually assign ownership? (Factory#611)
#
# A CODEOWNERS rule naming an account WITHOUT write access is ignored by GitHub
# in full. The file still sits in the repo root, still lists `*` and `/scripts/`
# and `/SECURITY.md` against a handle, and still reads to anyone opening the repo
# - an assessor included - as though those paths have a named owner. They do not.
#
# Measured 2026-08-07: PFactory, TFactory and AIFactory each carry a root
# CODEOWNERS assigning every path to @dataseeek, who is not a collaborator on any
# of them. GitHub's own validator reports all 8 rules in each file as "Unknown
# owner". Three files, 24 rules, zero ownership - and nothing anywhere noticed,
# which is the point. This is the exact shape docs/dev/gate-honesty.md calls a
# false pass: remove the control and nothing changes, because the control was
# never doing anything.
#
# Checked only where the intent table sets CODE_OWNER=1, since that is the
# declaration that the file is meant to be load-bearing. Note those three repos
# also have REVIEWS=0, so `require_code_owner_reviews` is not even reachable
# today (it lives inside the null required_pull_request_reviews block) - the file
# would still assign nothing on the day reviews are turned on, which is when
# somebody would otherwise discover this. See docs/compliance/agent-identity.md.
#
# Reads the GET /repos/{o}/{r}/codeowners/errors payload on stdin; prints CLEAN,
# UNPARSEABLE, or a one-line summary of the errors.
#
# A payload with no `errors` array is UNPARSEABLE, not CLEAN. `.errors // []`
# would have read a response shape this does not understand - a redirect body, an
# error envelope, a future API change - as "no problems found", which is the
# false-pass this whole check exists to catch, one level up (rule 4.7).
codeowners_verdict() {
  jq -r 'if (.errors | type) != "array" then "UNPARSEABLE"
         elif (.errors | length) == 0 then "CLEAN"
         else "\((.errors | length)) rule(s) assign no owner: "
              + ([.errors[] | "line \(.line) \(.kind)"] | join(", "))
         end'
}

# Offline introspection: no network, no token. Handled before anything reaches gh.
case "$MODE" in
  codeowners-stdin)
    codeowners_verdict
    exit 0 ;;
  emit)
    [ -n "$ONLY_REPO" ] && [ -n "$EMIT_BRANCH" ] || { echo "--emit needs REPO and BRANCH" >&2; exit 2; }
    build_payload "$ONLY_REPO" "$EMIT_BRANCH" | normalise
    exit 0 ;;
  normalise-stdin)
    normalise
    exit 0 ;;
esac

DIVERGED=0
UNDETERMINED=0

# Fetch live protection. Distinguishes the three 404-ish outcomes, because
# treating them alike is how a drift gate reports green without having read
# anything (rule 4.7):
#   "Branch not protected" -> a real, reportable divergence (live has none)
#   "Branch not found"     -> the intent names a branch that does not exist: ERROR
#   anything else (403 ...) -> the token cannot see protection: ERROR, not "no drift"
# Echoes the live JSON on success, or "NONE"; returns 2 when undetermined.
fetch_live() {
  local repo="$1" branch="$2" out
  if out="$(gh api "repos/${OWNER}/${repo}/branches/${branch}/protection" 2>/dev/null)"; then
    printf '%s' "$out"
    return 0
  fi
  local msg
  msg="$(jq -r '.message // "unparseable response"' <<<"${out:-{\}}" 2>/dev/null || echo "unparseable response")"
  case "$msg" in
    "Branch not protected") printf 'NONE'; return 0 ;;
    "Branch not found")
      echo "  ERROR: intent declares ${repo}@${branch} but that branch does not exist." >&2
      return 2 ;;
    *)
      echo "  ERROR: cannot read protection for ${repo}@${branch}: ${msg}" >&2
      echo "         Reading branch protection is an admin-only endpoint. The Actions" >&2
      echo "         GITHUB_TOKEN cannot be granted it (there is no 'administration'" >&2
      echo "         permission scope), so CI must supply an admin PAT." >&2
      return 2 ;;
  esac
}

check_one() {
  local repo="$1" branch="$2" intent live rc=0
  intent="$(build_payload "$repo" "$branch" | normalise)"
  live="$(fetch_live "$repo" "$branch")" || rc=$?
  if [ "$rc" != "0" ]; then
    UNDETERMINED=1
    return
  fi

  if [ "$live" = "NONE" ]; then
    echo "DRIFT ${OWNER}/${repo}@${branch}: branch has NO protection; intent declares protection."
    echo "$intent" | sed 's/^/    want: /'
    DIVERGED=1
    return
  fi

  local livenorm
  livenorm="$(normalise <<<"$live")"
  if [ "$livenorm" = "$intent" ]; then
    echo "ok    ${OWNER}/${repo}@${branch}"
    return
  fi

  echo "DRIFT ${OWNER}/${repo}@${branch}"
  diff <(jq -S . <<<"$intent") <(jq -S . <<<"$livenorm") \
    | sed -e 's/^</    want:/' -e 's/^>/    live:/' -e '/^---$/d' || true
  DIVERGED=1
}

# Refuse to weaken a branch (#691).
#
# The PUT below REPLACES required_status_checks wholesale, so any check that is
# live but missing from the table is silently dropped. That is how AIFactory@dev
# came to be one `--apply` away from losing its ratchet, its format gate and its
# shared-baseline drift gate: the table carried one CHECKS per repo and could
# not express that dev is gated more than main.
#
# The table being wrong is recoverable; applying it without noticing is not, and
# it fails OPEN - protection disappears and CI still goes green, so nothing
# announces it. This makes that specific direction loud. Adding checks, changing
# reviews, or any other divergence is unaffected: only REMOVAL is blocked.
assert_no_strip() {
  local repo="$1" branch="$2" payload="$3" live wanted lost
  live="$(gh api "repos/${OWNER}/${repo}/branches/${branch}/protection" \
            --jq '.required_status_checks.contexts // [] | .[]' 2>/dev/null || true)"
  [ -z "$live" ] && return 0
  wanted="$(jq -r '.required_status_checks.contexts // [] | .[]' <<<"$payload")"
  lost="$(comm -23 <(sort <<<"$live") <(sort <<<"$wanted"))"
  [ -z "$lost" ] && return 0

  echo "REFUSING to apply ${OWNER}/${repo}@${branch}: it would REMOVE required checks:" >&2
  while IFS= read -r c; do [ -n "$c" ] && echo "    - ${c}" >&2; done <<<"$lost"
  echo >&2
  echo "  These are live now and absent from the intent table. Either the table is" >&2
  echo "  stale (add them, as #691 did for AIFactory@dev), or the removal is" >&2
  echo "  deliberate - in which case re-run with ALLOW_STRIP=1 and say why in the" >&2
  echo "  commit that changes the table." >&2
  return 1
}

apply_one() {
  local repo="$1" branch="$2" payload
  payload="$(build_payload "$repo" "$branch")"
  echo "==================== ${OWNER}/${repo} : ${branch} ===================="
  echo "$payload" | jq .
  if [ "$MODE" = "apply" ]; then
    if [ "${ALLOW_STRIP:-0}" != "1" ]; then
      assert_no_strip "$repo" "$branch" "$payload" || return 1
    fi
    echo ">> PUT repos/${OWNER}/${repo}/branches/${branch}/protection"
    echo "$payload" | gh api -X PUT \
      -H "Accept: application/vnd.github+json" \
      "repos/${OWNER}/${repo}/branches/${branch}/protection" --input - >/dev/null
    echo ">> applied."
  else
    echo "(plan: nothing written. Re-run with --apply to enforce.)"
  fi
  echo
}

# Factory#467: the documented branching model was followed by 0 of 90 PRs, and
# the cause was mechanical rather than cultural - the repo default branch was
# `main`, and `gh pr create`, the web "Compare & pull request" button, Renovate
# and every agent in the fleet target the default when given no --base. The
# documentation said dev; the tooling default said main; the tooling won every
# time.
#
# Setting the default to `dev` fixed it: measured across the last 120 merged PRs,
# 89 went to dev and the other 31 are dev->main promotions, i.e. zero violations.
# But NOTHING asserted the setting, so one flip back would silently restore 0%
# compliance with no gate anywhere noticing - a written rule enforced by nothing,
# which is the defect class the issue itself names.
#
# CHECK ONLY, deliberately, and not for symmetry's sake. Changing a default
# branch redirects every future PR in the repo, and it is a one-line fix a human
# should make knowingly; a bug in an --apply path here would silently re-point
# the fleet. So this reports the exact command instead of running it.
check_default_branch() {
  local repo="$1" want="$2" live
  live="$(gh api "repos/${OWNER}/${repo}" --jq .default_branch 2>/dev/null)" || {
    echo "UNDETERMINED ${OWNER}/${repo}: could not read default_branch."
    UNDETERMINED=1
    return
  }
  if [ "$live" != "$want" ]; then
    echo "DRIFT ${OWNER}/${repo}: default branch is '${live}', intent is '${want}'."
    echo "    Every PR opened without an explicit --base goes to '${live}' (Factory#467)."
    echo "    Fix: gh api -X PATCH repos/${OWNER}/${repo} -f default_branch=${want}"
    DIVERGED=1
  fi
}

# Private vulnerability reporting, checked here because nothing else looked
# (CFactory#344). Every repo in this fleet is PUBLIC. Three of them shipped a
# SECURITY.md telling reporters to use GitHub's private reporting flow while the
# setting was OFF, so that flow refused the report and the only channel a
# reporter actually had was a public issue - the precise opposite of what the
# file asks for. A documented promise the platform will not honour.
#
# It is a fleet invariant rather than per-repo config: public repo, therefore a
# private disclosure route. Private repos are skipped because the setting is
# meaningless there, not because it is optional.
#
# CHECK ONLY, matching check_default_branch above rather than the protection
# object: enabling is a single PUT and the message carries it, so there is no
# --apply path to maintain for a one-line fix.
check_private_vuln_reporting() {
  local repo="$1" vis live
  vis="$(gh api "repos/${OWNER}/${repo}" --jq 'if .private then "private" else "public" end' 2>/dev/null)" || {
    echo "UNDETERMINED ${OWNER}/${repo}: could not read repo visibility."
    UNDETERMINED=1
    return
  }
  [ "$vis" = "public" ] || return 0
  live="$(gh api "repos/${OWNER}/${repo}/private-vulnerability-reporting" --jq .enabled 2>/dev/null)" || {
    echo "UNDETERMINED ${OWNER}/${repo}: could not read private-vulnerability-reporting."
    UNDETERMINED=1
    return
  }
  if [ "$live" != "true" ]; then
    echo "DRIFT ${OWNER}/${repo}: private vulnerability reporting is DISABLED on a public repo."
    echo "    A reporter following SECURITY.md has no private channel and must open a public issue."
    # `--method PUT` rather than the short flag form, and NOT a stylistic choice:
    # the intent test counts the short-flag write spelling in this file and
    # requires exactly ONE, so that --apply stays the only path that can write.
    # This string sits inside an echo and writes nothing, but a literal count
    # cannot tell the difference, and relaxing that assertion to let it through
    # would cost more than four characters. Identical command. Do not "tidy" it
    # back -- including in this comment, which is why it is not spelled here.
    echo "    Fix: gh api --method PUT repos/${OWNER}/${repo}/private-vulnerability-reporting"
    DIVERGED=1
  fi
}

# Live counterpart of codeowners_verdict(). CHECK ONLY - there is no --apply
# path, deliberately: the fix is either to grant the named account write access
# or to name a different one, and both are decisions about who reviews what.
check_codeowners() {
  local repo="$1" out msg verdict
  if out="$(gh api "repos/${OWNER}/${repo}/codeowners/errors" 2>/dev/null)"; then
    verdict="$(printf '%s' "$out" | codeowners_verdict)"
    if [ "$verdict" = "CLEAN" ]; then
      echo "ok    ${OWNER}/${repo} CODEOWNERS: every rule names an owner with write access"
      return
    fi
    if [ "$verdict" = "UNPARSEABLE" ]; then
      echo "  ERROR: ${repo}/codeowners/errors returned no errors array; not reading that as clean." >&2
      UNDETERMINED=1
      return
    fi
    echo "DRIFT ${OWNER}/${repo}: intent declares CODE_OWNER=1 but CODEOWNERS assigns no ownership."
    echo "    ${verdict}"
    echo "    GitHub ignores a rule whose owner lacks write access, so those paths have"
    echo "    no owner at all while the file reads as though they do (Factory#611)."
    echo "    Fix: gh api repos/${OWNER}/${repo}/codeowners/errors  # then grant that"
    echo "    account write access, or point the rules at one that has it."
    DIVERGED=1
    return
  fi
  msg="$(jq -r '.message // "unparseable response"' <<<"${out:-{\}}" 2>/dev/null || echo "unparseable response")"
  if [ "$msg" = "Not Found" ]; then
    echo "DRIFT ${OWNER}/${repo}: intent declares CODE_OWNER=1 but the repo has no CODEOWNERS file."
    DIVERGED=1
    return
  fi
  echo "  ERROR: cannot read CODEOWNERS validity for ${repo}: ${msg}" >&2
  UNDETERMINED=1
}

run_repo() {
  local repo="$1"
  repo_config "$repo"
  local branch
  if [ "$MODE" = "check" ]; then
    check_default_branch "$repo" "$DEFAULT_BRANCH"
    check_private_vuln_reporting "$repo"
    if [ "$CODE_OWNER" = "1" ]; then
      check_codeowners "$repo"
    fi
  fi
  for branch in $BRANCHES; do
    if [ "$MODE" = "check" ]; then
      check_one "$repo" "$branch"
    else
      apply_one "$repo" "$branch"
    fi
  done
}

# --signatures acts ONLY on required_signatures and never touches the protection
# object, so it must not fall through to the check summary below: that summary
# reports on a comparison this path never performed, and printing "OK: live
# branch protection matches the declared intent" after reading no live
# protection is the false-green shape rule 4.7 exists to prevent (Factory#642).
if [ "$SIGNATURES" = "1" ]; then
  if [ -n "$ONLY_REPO" ]; then
    signatures_one "$ONLY_REPO"
  else
    for r in "${ALL_REPOS[@]}"; do signatures_one "$r"; done
  fi
  if [ "$MODE" != "apply" ]; then
    echo "DRY-RUN complete. No signing requirement was changed. This is a plan only."
  fi
  exit 0
fi

if [ -n "$ONLY_REPO" ]; then
  run_repo "$ONLY_REPO"
else
  for r in "${ALL_REPOS[@]}"; do run_repo "$r"; done
fi

case "$MODE" in
  check)
    echo
    if [ "$UNDETERMINED" = "1" ]; then
      echo "UNDETERMINED: could not read live protection for at least one declared branch."
      echo "A check that cannot reach its input has verified nothing - failing instead of"
      echo "reporting green (standards/coding-standards.md rule 4.7)."
      exit 2
    fi
    if [ "$DIVERGED" = "1" ]; then
      echo "DRIFT: live branch protection does not match the declared intent above."
      echo "Either the intent is stale (update this script) or protection was changed by"
      echo "hand (re-run with --apply). Do not guess which - decide deliberately."
      exit 1
    fi
    echo "OK: live branch protection matches the declared intent for every declared branch."
    ;;
  plan)
    echo "PLAN complete. No protection was changed. Re-run with --apply to enforce."
    ;;
esac

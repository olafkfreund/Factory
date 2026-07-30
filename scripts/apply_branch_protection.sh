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
WITH_VERIFY="${WITH_VERIFY:-0}"   # 1 = also require the TFactory verification status (see docs, phase 3)

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) MODE="apply" ;;
    --check) MODE="check" ;;
    --plan|--dry-run) MODE="plan" ;;
    --repo) ONLY_REPO="${2:-}"; shift ;;
    # Introspection hooks, no network. --emit prints the NORMALISED intent for one
    # repo/branch; --normalise-stdin prints the normal form of a protection JSON
    # read from stdin. Together they let the comparator be tested offline: the two
    # must agree for a live response that matches intent, and disagree when one
    # field is changed (tests/test_branch_protection_intent.py, rule 4.9).
    --emit) MODE="emit"; ONLY_REPO="${2:-}"; EMIT_BRANCH="${3:-}"; shift 2 ;;
    --normalise-stdin) MODE="normalise-stdin" ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
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
#
# enforce_admins is 0 across the baseline so the factory's own auto-merge loop
# (admin token running `gh pr merge`) and the gitops CD bot keep working.
#
# CHECKS are per-repo because the repos' CI job names genuinely differ (CFactory
# names them "Backend pytest"/"Frontend typecheck + build"; the Python services
# use "backend (ruff + pytest)"). This table is the single place they are
# declared - the previous per-repo copies of this script each hardcoded one
# repo's names and were vendored into repos whose jobs are named differently.
repo_config() {
  case "$1" in
    CFactory)      CHECKS='["Backend pytest","Frontend typecheck + build"]'; REVIEWS=0; CODE_OWNER=0; ENFORCE_ADMINS=0; VERIFY=0; BRANCHES="main dev" ;;
    Factory)       CHECKS='["ruff + mypy ratchet (diff-scoped, blocking)","ruff format --check (scripts, blocking)","generated package self-test (pytest)"]'; REVIEWS=0; CODE_OWNER=0; ENFORCE_ADMINS=0; VERIFY=0; BRANCHES="main" ;;
    PFactory)      CHECKS='["backend (ruff + pytest)","critical (fast PR gate)"]'; REVIEWS=0; CODE_OWNER=1; ENFORCE_ADMINS=0; VERIFY=0; BRANCHES="main dev" ;;
    TFactory)      CHECKS='["backend (ruff + pytest)","critical (fast PR gate)"]'; REVIEWS=0; CODE_OWNER=1; ENFORCE_ADMINS=0; VERIFY=1; BRANCHES="main dev" ;;
    AIFactory)     CHECKS='["backend (ruff + pytest)"]'; REVIEWS=0; CODE_OWNER=1; ENFORCE_ADMINS=0; VERIFY=1; BRANCHES="main dev" ;;
    # gitops is bot-driven CD. Its manifests reach the live cluster through
    # ArgoCD, so until factory-gitops#95 it was the least gated repo in the
    # fleet with the highest blast radius; `kustomize build + schema` now runs
    # on every PR. Force-push and deletion stay blocked so ArgoCD's committed
    # history cannot be rewritten or dropped.
    factory-gitops) CHECKS='["kustomize build + schema"]'; REVIEWS=0; CODE_OWNER=0; ENFORCE_ADMINS=0; VERIFY=0; BRANCHES="main" ;;
    *) echo "no config for repo: $1" >&2; return 1 ;;
  esac
}

ALL_REPOS=(CFactory Factory PFactory TFactory AIFactory factory-gitops)

# Per-branch intent. `main` is the release branch: up-to-date-required, reviewed,
# conversations resolved. `dev` is the integration branch and is deliberately
# LOOSER: the same CI checks still gate every merge, but there is no review
# requirement, no strict up-to-date requirement and no conversation-resolution
# gate. That is not drift to be corrected - a solo maintainer (and the factory's
# own agents) have nobody to approve their PRs, so requiring a review on the
# integration branch would stall every merge, and `strict` would force a rebase
# before each one. See Factory#455 / Factory#468.
build_payload() {
  local repo="$1" branch="$2"
  repo_config "$repo"

  local checks="$CHECKS" strict reviews convres
  case "$branch" in
    main) strict=true;  reviews="$REVIEWS"; convres=true ;;
    dev)  strict=false; reviews=0;          convres=false ;;
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

# Offline introspection: no network, no token. Handled before anything reaches gh.
case "$MODE" in
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

apply_one() {
  local repo="$1" branch="$2" payload
  payload="$(build_payload "$repo" "$branch")"
  echo "==================== ${OWNER}/${repo} : ${branch} ===================="
  echo "$payload" | jq .
  if [ "$MODE" = "apply" ]; then
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

run_repo() {
  local repo="$1"
  repo_config "$repo"
  local branch
  for branch in $BRANCHES; do
    if [ "$MODE" = "check" ]; then
      check_one "$repo" "$branch"
    else
      apply_one "$repo" "$branch"
    fi
  done
}

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

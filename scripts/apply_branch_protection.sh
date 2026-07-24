#!/usr/bin/env bash
# Branch-protection-as-code for the Factory fleet (Factory#316).
#
# Codifies the intended `main` protection for every repo in the program and
# applies it idempotently via the GitHub classic branch-protection API. It is
# DRY-RUN by default: it prints the exact payload it WOULD PUT and changes
# nothing. Protection is only written when you pass --apply.
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
#   scripts/apply_branch_protection.sh                 # dry-run ALL repos (default)
#   scripts/apply_branch_protection.sh --repo CFactory # dry-run one repo
#   scripts/apply_branch_protection.sh --apply --repo CFactory   # APPLY one repo
#   scripts/apply_branch_protection.sh --apply         # APPLY all repos
#   WITH_VERIFY=1 scripts/apply_branch_protection.sh --repo AIFactory
#                                                      # include TFactory verify check
#
# Requires: gh (authenticated with admin on the repos) and jq.
# Idempotent: PUT replaces the whole protection object, so re-running converges.
set -euo pipefail

OWNER="olafkfreund"
APPLY=0
ONLY_REPO=""
WITH_VERIFY="${WITH_VERIFY:-0}"   # 1 = also require the TFactory verification status (see docs, phase 3)

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --dry-run) APPLY=0 ;;
    --repo) ONLY_REPO="${2:-}"; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

command -v gh >/dev/null || { echo "gh not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq not found" >&2; exit 1; }

# The TFactory verification status context (posted by copilot-pr-test.yml /
# pr-review-tests.yml). Only make it a REQUIRED check once you have confirmed it
# posts on EVERY pull request for that repo — otherwise it blocks PRs that never
# got a TFactory run. Off by default; enable with WITH_VERIFY=1.
VERIFY_CTX="tfactory/suite"

# Per-repo intended protection. Fields:
#   checks       : required status-check contexts (job display names / status contexts)
#   reviews      : 1 = require a PR with >=1 approving review; 0 = no PR-review requirement
#   code_owner   : 1 = require_code_owner_reviews (only where a CODEOWNERS file exists)
#   enforce_admins: 0 = admins (and admin-owned automation tokens) bypass; 1 = no bypass
#   verify       : 1 = eligible to also require $VERIFY_CTX when WITH_VERIFY=1
#
# enforce_admins is 0 across the baseline so the factory's own auto-merge loop
# (admin token running `gh pr merge`) and the gitops CD bot keep working. Tighten
# to 1 per repo only after confirming no automation relies on the bypass — see
# the rollout section of the docs.
repo_config() {
  case "$1" in
    # least-risky pilots first (see rollout order in the docs)
    CFactory)      CHECKS='["Backend pytest","Frontend typecheck + build"]'; REVIEWS=1; CODE_OWNER=0; ENFORCE_ADMINS=0; VERIFY=0 ;;
    Factory)       CHECKS='["ruff + mypy ratchet (diff-scoped, blocking)","ruff format --check (scripts, blocking)"]'; REVIEWS=1; CODE_OWNER=0; ENFORCE_ADMINS=0; VERIFY=0 ;;
    PFactory)      CHECKS='["backend (ruff + pytest)","critical (fast PR gate)"]'; REVIEWS=1; CODE_OWNER=1; ENFORCE_ADMINS=0; VERIFY=0 ;;
    TFactory)      CHECKS='["backend (ruff + pytest)","critical (fast PR gate)"]'; REVIEWS=1; CODE_OWNER=1; ENFORCE_ADMINS=0; VERIFY=1 ;;
    AIFactory)     CHECKS='["backend (ruff + pytest)"]'; REVIEWS=1; CODE_OWNER=1; ENFORCE_ADMINS=0; VERIFY=1 ;;
    # gitops is bot-driven CD: NO PR-review requirement (would rely entirely on
    # the admin bypass); protect only against force-push and branch deletion so
    # ArgoCD's committed history cannot be rewritten or dropped.
    factory-gitops) CHECKS='[]'; REVIEWS=0; CODE_OWNER=0; ENFORCE_ADMINS=0; VERIFY=0 ;;
    *) echo "no config for repo: $1" >&2; return 1 ;;
  esac
}

ALL_REPOS=(CFactory Factory PFactory TFactory AIFactory factory-gitops)

build_payload() {
  local repo="$1"
  repo_config "$repo"

  local checks="$CHECKS"
  if [ "$WITH_VERIFY" = "1" ] && [ "$VERIFY" = "1" ]; then
    checks="$(jq -c --arg c "$VERIFY_CTX" '. + [$c]' <<<"$checks")"
  fi

  # required_status_checks: null when there are no checks (gitops)
  local rsc="null"
  if [ "$(jq 'length' <<<"$checks")" -gt 0 ]; then
    rsc="$(jq -c --argjson ctx "$checks" '{strict: true, contexts: $ctx}' <<<'{}')"
  fi

  # required_pull_request_reviews: null when reviews not required (gitops)
  local rpr="null"
  if [ "$REVIEWS" = "1" ]; then
    rpr="$(jq -cn --argjson co "$CODE_OWNER" \
      '{required_approving_review_count: 1, require_code_owner_reviews: ($co==1), dismiss_stale_reviews: true}')"
  fi

  jq -cn \
    --argjson rsc "$rsc" \
    --argjson rpr "$rpr" \
    --argjson ea "$ENFORCE_ADMINS" \
    '{
      required_status_checks: $rsc,
      enforce_admins: ($ea==1),
      required_pull_request_reviews: $rpr,
      restrictions: null,
      allow_force_pushes: false,
      allow_deletions: false,
      required_linear_history: false,
      required_conversation_resolution: true
    }'
}

apply_one() {
  local repo="$1" payload
  payload="$(build_payload "$repo")"
  echo "==================== ${OWNER}/${repo} : main ===================="
  echo "$payload" | jq .
  if [ "$APPLY" = "1" ]; then
    echo ">> PUT repos/${OWNER}/${repo}/branches/main/protection"
    echo "$payload" | gh api -X PUT \
      -H "Accept: application/vnd.github+json" \
      "repos/${OWNER}/${repo}/branches/main/protection" --input - >/dev/null
    echo ">> applied."
  else
    echo "(dry-run: nothing written. Re-run with --apply to enforce.)"
  fi
  echo
}

if [ -n "$ONLY_REPO" ]; then
  apply_one "$ONLY_REPO"
else
  for r in "${ALL_REPOS[@]}"; do apply_one "$r"; done
fi

if [ "$APPLY" = "0" ]; then
  echo "DRY-RUN complete. No protection was changed. This is a plan only."
fi

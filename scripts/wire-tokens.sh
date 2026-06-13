#!/usr/bin/env bash
# Wire the Factory program's CI token secrets across all repos, consistently.
#
# This sets ONLY the secrets you provide a value for — blank input skips a secret,
# so re-running is safe and idempotent. It never prints token values.
#
# See docs/dev/secrets-and-tokens.md for what each token is and where to get it.
#
# Usage:
#   scripts/wire-tokens.sh                 # interactive: prompts for each token
#   FACTORY_TOKEN=acw_xxx \
#     scripts/wire-tokens.sh --only factory-token   # non-interactive, one token
#   scripts/wire-tokens.sh --dry-run       # show what WOULD be set, set nothing
#
# Requires: gh (authenticated with admin on the repos).
set -euo pipefail

OWNER="olafkfreund"
SEAM_REPOS=(Factory AIFactory PFactory TFactory CFactory)  # where seam-check / nightly read FACTORY_TOKEN

DRY_RUN=false
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=true ;;
    --only) ONLY="${2:-}"; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

command -v gh >/dev/null || { echo "gh not found" >&2; exit 1; }

# set_secret NAME VALUE REPO...
set_secret() {
  local name="$1" value="$2"; shift 2
  [ -z "$value" ] && { echo "  - $name: (no value given, skipped)"; return; }
  for repo in "$@"; do
    if $DRY_RUN; then
      echo "  - would set $name on $OWNER/$repo"
    else
      printf '%s' "$value" | gh secret set "$name" --repo "$OWNER/$repo" --body - \
        && echo "  - set $name on $OWNER/$repo"
    fi
  done
}

# prompt_secret VAR_NAME PROMPT  -> reads hidden input into the named variable,
# unless it is already set in the environment.
prompt_secret() {
  local var="$1" prompt="$2" current="${!1:-}"
  if [ -n "$current" ]; then return; fi
  read -rsp "$prompt (blank to skip): " "$var" </dev/tty || true
  echo
}

want() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

echo "Wiring Factory CI tokens (owner: $OWNER)${DRY_RUN:+ [dry-run]}"
echo "Nothing is printed; blank input skips. See docs/dev/secrets-and-tokens.md."
echo

# --- Seam-gate fleet token: FACTORY_TOKEN on all repos that run the gate ---
if want factory-token; then
  echo "FACTORY_TOKEN — fleet bearer token for the PARR seam regression"
  echo "  (a scoped acw_ key with write scope, or APP_API_TOKEN; see the docs)"
  prompt_secret FACTORY_TOKEN "  value"
  set_secret FACTORY_TOKEN "${FACTORY_TOKEN:-}" "${SEAM_REPOS[@]}"
  echo
fi

# --- Per-service API tokens (dispatch + copilot review) ---
if want service-tokens; then
  echo "Per-service API tokens (used by aifactory:run / copilot review):"
  prompt_secret AIFACTORY_TOKEN "  AIFACTORY_TOKEN"
  set_secret AIFACTORY_TOKEN "${AIFACTORY_TOKEN:-}" AIFactory
  prompt_secret PFACTORY_TOKEN "  PFACTORY_TOKEN"
  set_secret PFACTORY_TOKEN "${PFACTORY_TOKEN:-}" PFactory
  prompt_secret TFACTORY_TOKEN "  TFACTORY_TOKEN"
  set_secret TFACTORY_TOKEN "${TFACTORY_TOKEN:-}" TFactory
  echo
fi

# --- Service URLs. IMPORTANT: only set these alongside the matching *_TOKEN, ---
# --- or the workflow will route at the live API and fail auth (see docs).    ---
if want service-urls; then
  echo "Service URLs (set ONLY together with the matching token above):"
  : "${AIFACTORY_URL:=https://aifactory.freundcloud.org.uk}"
  : "${PFACTORY_URL:=https://pfactory.freundcloud.org.uk}"
  read -rp "  set AIFACTORY_URL=$AIFACTORY_URL on AIFactory? [y/N] " a </dev/tty || true
  [ "${a:-}" = "y" ] && set_secret AIFACTORY_URL "$AIFACTORY_URL" AIFactory
  read -rp "  set PFACTORY_URL=$PFACTORY_URL on PFactory? [y/N] " p </dev/tty || true
  [ "${p:-}" = "y" ] && set_secret PFACTORY_URL "$PFACTORY_URL" PFactory
  echo
fi

echo "Done. Verify (shows names only, never values):"
echo "  for r in ${SEAM_REPOS[*]}; do echo \"\$r:\"; gh secret list --repo $OWNER/\$r; done"

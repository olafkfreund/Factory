#!/bin/sh
# Open the quarterly access-review issue (Factory#312) unless one already exists.
# Quarter = the one that just ended (Jan -> previous year Q4, Apr -> Q1, Jul -> Q2, Oct -> Q3);
# set QUARTER=YYYY-Qn to open a specific one. Needs gh and GH_TOKEN with issues: write.
set -eu
TEMPLATE="${TEMPLATE:-docs/compliance/access-review-record-template.md}"

if [ -z "${QUARTER:-}" ]; then
  y=${YEAR:-$(date -u +%Y)}; m=${MONTH:-$(date -u +%m)}   # YEAR and MONTH: for tests
  case "$m" in
    01) QUARTER="$((y - 1))-Q4" ;;
    04) QUARTER="$y-Q1" ;;
    07) QUARTER="$y-Q2" ;;
    10) QUARTER="$y-Q3" ;;
    *) echo "month $m is not a quarter start; set QUARTER to open one" >&2; exit 1 ;;
  esac
fi
case "$QUARTER" in [0-9][0-9][0-9][0-9]-Q[1-4]) ;; *) echo "bad QUARTER '$QUARTER'" >&2; exit 1 ;; esac

title="Access review $QUARTER"
# --state all: a closed (completed) review must not be reopened by a rerun.
existing=$(gh issue list --state all --search "\"$title\" in:title" --json title --jq '.[].title') || exit 1
if printf '%s\n' "$existing" | grep -qxF "$title"; then
  echo "exists: $title"
  exit 0
fi

body=$(mktemp); trap 'rm -f "$body"' EXIT
# Relative links would resolve against the issue URL: point them at the repo.
base="https://github.com/${GH_REPO:-olafkfreund/Factory}/blob/main/docs/compliance"
sed -e "s/<YYYY>-Q<n>/$QUARTER/g" -e "s#](\([a-z0-9-]*\.md\))#]($base/\1)#g" "$TEMPLATE" >"$body"
gh issue create --title "$title" --body-file "$body"

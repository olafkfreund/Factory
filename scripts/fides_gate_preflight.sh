#!/usr/bin/env bash
# Fail-closed preflight for the Fides change gate (Factory#541, #331).
#
# Two properties, both of which the inline workflow version got wrong in one
# direction or the other:
#
#  1. A missing setting is a FAILURE, not a skip. FIDES_SERVER_URL /
#     FIDES_API_TOKEN / FLOW_ID are each required; unset OR empty is red. This
#     matches the #471/#500 rule that a missing token fails the gate.
#
#  2. An install step that installs nothing is a vacuous pass. The original
#     `curl -sSfL "$URL/cli/install.sh" | sh` runs under Actions' `bash -e {0}`,
#     which has no `pipefail`: against the Fides server deployed in this cluster
#     that URL 404s, curl exits 22, `sh` exits 0, and THE STEP GOES GREEN having
#     installed nothing. Verified 2026-08-07. So: no pipe, and the presence of
#     the `fides` binary is asserted afterwards rather than assumed.
#
# No setting value is ever echoed -- FIDES_API_TOKEN is a credential.
#
# Usage: scripts/fides_gate_preflight.sh
# Exit:  0 preflight passed and `fides` is on PATH; 1 otherwise.
set -euo pipefail

fail() {
    printf 'fides-gate preflight FAILED: %s\n' "$1" >&2
    exit 1
}

# Enumerate what was checked, on both the pass and the fail path -- a gate that
# prints only its failures leaves "reported present while absent" invisible
# (docs/dev/gate-honesty.md).
missing=()
for setting in FIDES_SERVER_URL FIDES_API_TOKEN FLOW_ID; do
    if [ -z "${!setting:-}" ]; then
        missing+=("$setting")
        printf '  %-18s MISSING\n' "$setting" >&2
    else
        printf '  %-18s set\n' "$setting" >&2
    fi
done

if [ ${#missing[@]} -gt 0 ]; then
    fail "unset or empty: ${missing[*]} (secrets FIDES_SERVER_URL/FIDES_CI_KEY, variable FIDES_FLOW_ID)"
fi

installer="$(mktemp)"
trap 'rm -f "$installer"' EXIT

# Separate steps, so an HTTP error is this script's exit status and not the
# exit status of an `sh` that read an empty stdin.
curl -sSfL "${FIDES_SERVER_URL%/}/cli/install.sh" -o "$installer" \
    || fail "cannot fetch ${FIDES_SERVER_URL%/}/cli/install.sh (server unreachable from this runner, or it does not serve the CLI installer)"

sh "$installer" || fail "the Fides CLI installer exited non-zero"

# The installer succeeding is not the same claim as the CLI existing.
command -v fides >/dev/null 2>&1 \
    || fail "installer completed but 'fides' is not on PATH"

printf 'fides-gate preflight OK: 3/3 settings present, fides CLI at %s\n' "$(command -v fides)" >&2

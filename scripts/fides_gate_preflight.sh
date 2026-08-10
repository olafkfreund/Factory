#!/usr/bin/env bash
# Preflight for the Fides change gate (Factory#541, Factory#316).
#
# Replaces two steps that each reported success without having done their job:
#
#   1. A settings check that read unset and empty alike as "present".
#   2. `curl -sSfL "$FIDES_SERVER_URL/cli/install.sh" | sh`
#
# The second is the interesting one. GitHub Actions runs `run:` under
# `bash -e {0}` with NO `pipefail`, so in that pipeline curl's failure is
# discarded and only `sh`'s status survives. `sh` reading empty stdin exits 0.
# Measured against the live server, which does not serve that path:
#
#   /                200
#   /cli/install.sh  404
#   bash -e, no pipefail:  curl: (22) ... 404   ->  exit 0
#   with pipefail:         curl: (22) ... 404   ->  exit 22
#
# So the step reported success having installed nothing, and the real failure
# surfaced two steps later as `fides: command not found`. That is the shape
# catalogued in Factory#642: the status channel reported on the process, not on
# the artefact.
#
# This script holds three properties:
#
#   - a missing setting is red, unset and empty alike, every one enumerated on
#     the pass path as well as the fail path, and no value is ever echoed;
#   - the CLI is fetched to a FILE, never piped, so an HTTP error is this
#     script's exit status;
#   - the download is checked against a digest pinned HERE, not against a
#     checksum fetched from the same place as the tarball -- a checksum served
#     alongside the artefact proves transfer integrity, not provenance, and
#     moves with the artefact if the source is ever tampered with;
#   - `command -v fides` is ASSERTED, not assumed. An install that installed
#     nothing is red.
#
# Usage: scripts/fides_gate_preflight.sh [--bindir DIR]
# Exit:  0 ready (fides on PATH), 1 a setting is missing, 2 the install failed.
set -euo pipefail

# Pinned CLI release. Bump both together; the digest is of the linux_amd64
# tarball published at this tag. Verified locally before pinning.
FIDES_CLI_VERSION="${FIDES_CLI_VERSION:-v0.4.0}"
FIDES_CLI_SHA256="${FIDES_CLI_SHA256:-db2bca7fb10553cd9b526089db65d1bd3f19bf08680d6fdcd99d9c2b12a89d6a}"
FIDES_CLI_REPO="${FIDES_CLI_REPO:-olafkfreund/fides}"

BINDIR="${HOME}/.local/bin"
while [ $# -gt 0 ]; do
  case "$1" in
    --bindir) BINDIR="${2:-}"; shift ;;
    -h|--help) sed -n '2,45p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

# ---------------------------------------------------------------- settings
# Enumerated on BOTH paths. A check that lists what it verified only when it
# fails cannot be audited when it passes.
missing=0
for var in FIDES_SERVER_URL FIDES_API_TOKEN FIDES_FLOW_ID; do
  # ${!var} is empty for unset AND for set-but-empty. Treating those
  # differently is how a gate runs against a blank token and reports a verdict
  # it never obtained.
  if [ -z "${!var:-}" ]; then
    echo "MISSING: ${var} is unset or empty" >&2
    missing=1
  else
    echo "present: ${var}"   # never the value
  fi
done
if [ "$missing" = "1" ]; then
  echo >&2
  echo "The Fides change gate cannot run without all three. Set FIDES_SERVER_URL" >&2
  echo "and FIDES_API_TOKEN as repository secrets and FIDES_FLOW_ID as a variable." >&2
  echo "Failing closed: a gate that cannot reach its input has verified nothing" >&2
  echo "(standards/coding-standards.md rule 4.7)." >&2
  exit 1
fi

# ---------------------------------------------------------------- install
if command -v fides >/dev/null 2>&1; then
  echo "fides already on PATH: $(command -v fides)"
  exit 0
fi

mkdir -p "$BINDIR"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

tarball="fides_${FIDES_CLI_VERSION}_linux_amd64.tar.gz"
url="https://github.com/${FIDES_CLI_REPO}/releases/download/${FIDES_CLI_VERSION}/${tarball}"

echo "downloading ${url}"
# -f makes an HTTP error a curl failure; -o writes a file rather than piping to
# a shell, so that failure is this script's exit status and cannot be swallowed
# by a downstream `sh` that exits 0 on empty stdin.
if ! curl -sSfL --retry 3 --retry-delay 2 -o "${tmp}/${tarball}" "$url"; then
  echo "ERROR: could not download the Fides CLI from ${url}" >&2
  exit 2
fi

echo "${FIDES_CLI_SHA256}  ${tmp}/${tarball}" | sha256sum -c - || {
  echo "ERROR: checksum mismatch for ${tarball}." >&2
  echo "       Expected ${FIDES_CLI_SHA256}." >&2
  echo "       Refusing to install. If the release was re-cut, verify the new" >&2
  echo "       digest deliberately and update FIDES_CLI_SHA256 in this script." >&2
  exit 2
}

tar -xzf "${tmp}/${tarball}" -C "$tmp"
# The tarball unpacks into a versioned directory containing several binaries;
# take only the CLI.
found="$(find "$tmp" -type f -name fides -perm -u+x | head -1)"
if [ -z "$found" ]; then
  echo "ERROR: the archive contained no 'fides' executable." >&2
  exit 2
fi
install -m 0755 "$found" "${BINDIR}/fides"
export PATH="${BINDIR}:${PATH}"

# The assertion the old step never made. Everything above can look fine and
# still leave nothing runnable on PATH.
if ! command -v fides >/dev/null 2>&1; then
  echo "ERROR: install completed but 'fides' is not on PATH (${BINDIR})." >&2
  exit 2
fi

echo "installed: $(command -v fides) (${FIDES_CLI_VERSION})"
echo "$BINDIR" >> "${GITHUB_PATH:-/dev/null}"

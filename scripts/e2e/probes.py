"""Specific-reason oracles for controlled negative probes a-m."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Probe:
    stage: str
    reason: str
    pattern: str


PROBES = {
    "a": Probe("S1", "idempotent onboarding", r"(?:already exists|deduplicat|idempotent)"),
    "b": Probe(
        "S1",
        "repo access denied",
        r"(?:repo|repository).*(?:inaccessible|access denied|cannot access)",
    ),
    "c": Probe(
        "S2", "artifact integrity rejection", r"(?:artifact|blob).*(?:integrity|sha|hash mismatch)"
    ),
    "d": Probe(
        "S2",
        "signed-plan rejection",
        r"(?:signed.plan|signature|contract).*(?:invalid|mismatch|reject)",
    ),
    "e": Probe("S2", "deduplicated task", r"(?:deduplicat|already (?:submitted|exists))"),
    "f": Probe("S3", "empty or docs-only diff", r"(?:empty diff|no code changes|docs.only)"),
    "g": Probe("S3", "missing usage", r"missing usage"),
    "h": Probe("S4", "stale verdict", r"(?:stale|head.*changed|verdict.*sha.*mismatch)"),
    "i": Probe("S5", "zero tests", r"(?:zero|0|no) tests"),
    "j": Probe(
        "S5", "verdict SHA mismatch", r"(?:verdict|merge).*(?:sha|commit).*(?:mismatch|different)"
    ),
    "k": Probe(
        "S5", "P4 mutant behaviour", r"(?:mutant|planted bug|behavio[u]?r).*(?:fail|red|broken)"
    ),
    "l": Probe("X", "duplicate event ignored", r"(?:duplicate|already applied|deduplicat)"),
    "m": Probe("X", "issue isolation", r"(?:isolat|distinct repos|no bleed)"),
}
HTTP_OK = 200
HTTP_REDIRECT = 300
HTTP_CLIENT_ERROR = 400
HTTP_SERVER_ERROR = 500
PAIR_SIZE = 2


def matches(probe: str, status: int, reason: str) -> bool:
    if not (
        HTTP_OK <= status < HTTP_REDIRECT or HTTP_CLIENT_ERROR <= status < HTTP_SERVER_ERROR
    ) or status in {401, 403, 404}:
        return False
    return bool(re.search(PROBES[probe].pattern, reason, flags=re.IGNORECASE))


def verify(
    probe: str, status: int, reason: str, *, before: object = None, after: object = None
) -> None:
    if not matches(probe, status, reason):
        raise AssertionError(f"probe {probe}: expected {PROBES[probe].reason}")
    if probe in {"a", "e", "l"} and (before is None or after is None or before != after):
        raise AssertionError(f"probe {probe}: replay changed resource count")
    if probe == "m" and (
        not isinstance(after, tuple) or len(after) != PAIR_SIZE or after[0] == after[1]
    ):
        raise AssertionError("probe m: cards bled across repositories")

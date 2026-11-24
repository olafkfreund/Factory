"""Specific-reason oracles for controlled negative probes a-m."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Probe:
    stage: str
    reason: str
    pattern: str


PROBES = {
    "a": Probe("S1", "idempotent onboarding", r"\b(?:already exists|deduplicat\w*|idempotent)\b"),
    "b": Probe(
        "S1",
        "repo access denied",
        r"\b(?:repo|repository)\b.*\b(?:inaccessible|access denied|cannot access)\b",
    ),
    "c": Probe(
        "S2",
        "artifact integrity rejection",
        r"\b(?:artifact|blob)\b.*\b(?:integrity|sha|hash mismatch)\b",
    ),
    "d": Probe(
        "S2",
        "signed-plan rejection",
        r"\b(?:signed.plan|signature|contract)\b.*\b(?:invalid|mismatch|reject\w*)\b",
    ),
    "e": Probe("S2", "deduplicated task", r"\b(?:deduplicat\w*|already (?:submitted|exists))\b"),
    "f": Probe("S3", "empty or docs-only diff", r"\b(?:empty diff|no code changes|docs.only)\b"),
    "g": Probe("S3", "missing usage", ""),
    "h": Probe("S4", "stale verdict", r"\b(?:stale|head.*changed|verdict.*sha.*mismatch)\b"),
    "i": Probe("S5", "zero tests", r"\b(?:zero|0) tests\b"),
    "j": Probe(
        "S5",
        "verdict SHA mismatch",
        r"\b(?:verdict|merge)\b.*\b(?:sha|commit)\b.*\b(?:mismatch|different)\b",
    ),
    "k": Probe(
        "S5",
        "P4 mutant behaviour",
        r"\b(?:mutant|planted bug|behavio[u]?r)\b.*\b(?:fail\w*|red|broken)\b",
    ),
    "l": Probe("X", "duplicate event ignored", r"\b(?:duplicate|already applied|deduplicat\w*)\b"),
    "m": Probe("X", "issue isolation", ""),
}
HTTP_OK = 200
HTTP_REDIRECT = 300
HTTP_SERVER_ERROR = 500
HTTP_CONFLICT = 409
PAIR_SIZE = 2
REJECTIONS = {"c", "d", "j"}
REPLAY = {"a", "e", "l"}
BANNED = {401, 403, 404, 405, 407, 408, 429}


def matches(  # noqa: PLR0913
    probe: str,
    status: int,
    reason: str,
    *,
    code: str | None = None,
    field: str | None = None,
    after: object = None,
) -> bool:
    if status in BANNED or status >= HTTP_SERVER_ERROR or status < HTTP_OK:
        return False
    if probe in REJECTIONS | {"b", "f"}:
        allowed = status in {400, 409, 422}
    elif probe == "h":
        allowed = status == HTTP_CONFLICT
    else:
        allowed = HTTP_OK <= status < HTTP_REDIRECT or status == HTTP_CONFLICT
    if not allowed:
        return False
    if probe == "g":
        return (
            isinstance(after, dict)
            and after.get("total_tokens") == 0
            and after.get("deadline_reached") is True
        )
    if probe == "m":
        return isinstance(after, (tuple, list)) and len(after) == PAIR_SIZE and after[0] != after[1]
    if probe == "d" and re.search(
        r"\b(?:auth|unauthori[sz]ed|forbidden|permission)\b", reason, re.I
    ):
        return False
    source = " ".join(part for part in (code, field) if part) or reason
    source = re.sub(r"[_-]", " ", source)
    return bool(re.search(PROBES[probe].pattern, source, flags=re.IGNORECASE))


def verify(  # noqa: PLR0913
    probe: str,
    status: int,
    reason: str = "",
    *,
    before: object = None,
    after: object = None,
    code: str | None = None,
    field: str | None = None,
) -> None:
    if not matches(probe, status, reason, code=code, field=field, after=after):
        raise AssertionError(f"probe {probe}: expected {PROBES[probe].reason}")
    if probe in REPLAY and (before is None or after is None or before != after):
        raise AssertionError(f"probe {probe}: replay changed resource count")

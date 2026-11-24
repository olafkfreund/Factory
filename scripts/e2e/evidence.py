"""Persist only known evidence fields, with credential redaction."""

import re

SECRET = re.compile(r"(?i)(?:\bBearer\s+|\b(?:acw_|cfk_|ghp_|github_pat_))[A-Za-z0-9_\-.]+")
STAGE_FIELDS = {
    "registered",
    "branch_protection",
    "projects",
    "cards",
    "ingested",
    "approved",
    "emitted",
    "from_plan",
    "task_id",
    "cost_usd",
    "needs_you",
    "review_findings",
    "terminal",
    "green",
    "code_diff",
    "plan_files_only",
    "review_recorded",
    "reviewer_model",
    "coder_model",
    "runtime_models",
    "merged_by_service",
    "checks_green",
    "triple_linked",
    "merged_head",
    "checked_head",
    "verdict_sha",
    "merge_sha",
    "hidden_suite_sha",
    "signals",
    "hidden_green",
    "events_ordered",
    "registry_filtered",
    "cost_reconciled",
    "no_card_anomaly",
    "probes",
}
PROBE_FIELDS = {"status", "reason", "code", "field", "before", "after"}


def redact(value: object) -> object:
    if isinstance(value, str):
        return SECRET.sub("[REDACTED]", value)
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def safe_fields(row: dict, allowed: set[str]) -> dict:
    selected = {key: row[key] for key in allowed if key in row}
    if "stage_results" in selected:
        selected["stage_results"] = {
            stage: safe_fields(result, STAGE_FIELDS)
            for stage, result in selected["stage_results"].items()
            if stage in {"S1", "S2", "S3", "S4", "S5", "X"} and isinstance(result, dict)
        }
    if "probes" in selected:
        selected["probes"] = {
            probe: safe_fields(result, PROBE_FIELDS)
            for probe, result in selected["probes"].items()
            if probe in "abcdefghijklm" and isinstance(result, dict)
        }
    return redact(selected)

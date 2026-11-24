"""Append-only identity ledger. A row is durable before its create returns."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.e2e.evidence import safe_fields

SERVICES = ("github", "aifactory", "pfactory", "tfactory", "cfactory")
KIND_SERVICES = {
    "repo": {"github"},
    "project": {"aifactory", "pfactory", "tfactory"},
    "session": {"pfactory"},
    "task": {"aifactory"},
    "spec": {"tfactory"},
    "card": {"cfactory"},
}
KINDS = {*KIND_SERVICES, "intent", "retained", "deleted", "create_failed", "failed"}


class Registry:
    def __init__(self, campaign: str, root: Path = Path("evidence")) -> None:
        self.path = root / campaign / "registry.jsonl"

    def append(
        self, kind: str, identity: str, repo_node_id: str, **fields: object
    ) -> dict[str, Any]:
        service = fields.get("service")
        target_kind = fields.get("target_kind")
        if kind == "intent":
            valid = service == "github" and target_kind == "repo" and identity == repo_node_id
        elif kind in {"deleted", "retained", "failed", "create_failed"}:
            valid = target_kind in KIND_SERVICES and service in KIND_SERVICES[target_kind]
            valid = valid and (kind != "retained" or target_kind == "session")
            valid = valid and (kind != "create_failed" or target_kind == "repo")
        else:
            valid = kind in KIND_SERVICES and service in KIND_SERVICES[kind] and target_kind is None
        if not valid or not identity or not repo_node_id:
            raise ValueError("invalid registry identity")
        entry = {
            "at": datetime.now(UTC).isoformat(),
            "kind": kind,
            "id": identity,
            "repo_node_id": repo_node_id,
            **safe_fields(fields, {"service", "target_kind", "repo_id", "full_name", "name"}),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(entry, sort_keys=True) + "\n")
            out.flush()
            os.fsync(out.fileno())
        return entry

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def find(self, service: str, kind: str, identity: str) -> dict[str, Any] | None:
        return next(
            (
                entry
                for entry in reversed(self.entries())
                if entry["service"] == service and entry["kind"] == kind and entry["id"] == identity
            ),
            None,
        )

    def active(self) -> list[dict[str, Any]]:
        entries = self.entries()
        ended = {
            (entry["service"], entry["repo_node_id"], entry["target_kind"], entry["id"])
            for entry in entries
            if entry["kind"] in {"deleted", "retained"}
        }
        active = {}
        for entry in entries:
            key = (entry["service"], entry["repo_node_id"], entry["kind"], entry["id"])
            if entry["kind"] in KIND_SERVICES and key not in ended:
                active[key] = entry
        return list(active.values())

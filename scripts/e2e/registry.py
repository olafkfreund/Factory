"""Append-only identity ledger. A row is durable before its create returns."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

SERVICES = ("aifactory", "pfactory", "tfactory", "cfactory")
KINDS = {"repo", "project", "session", "task", "spec", "card", "retained", "deleted"}


class Registry:
    def __init__(self, campaign: str, root: Path = Path("evidence")) -> None:
        self.path = root / campaign / "registry.jsonl"

    def append(self, kind: str, identity: str, repo_node_id: str, **fields: object) -> dict:
        if kind not in KINDS or not identity or not repo_node_id:
            raise ValueError("invalid registry identity")
        entry = {
            "at": datetime.now(UTC).isoformat(),
            "kind": kind,
            "id": identity,
            "repo_node_id": repo_node_id,
            **fields,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(entry, sort_keys=True) + "\n")
            out.flush()
            os.fsync(out.fileno())
        return entry

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def find(self, kind: str, identity: str) -> dict | None:
        return next(
            (
                entry
                for entry in reversed(self.entries())
                if entry["kind"] == kind and entry["id"] == identity
            ),
            None,
        )

    def active(self) -> list[dict]:
        entries = self.entries()
        ended = {
            (entry["repo_node_id"], entry["target_kind"], entry["id"])
            for entry in entries
            if entry["kind"] in {"deleted", "retained"}
        }
        active = {}
        for entry in entries:
            key = (entry["repo_node_id"], entry["kind"], entry["id"])
            if entry["kind"] not in {"deleted", "retained"} and key not in ended:
                active[key] = entry
        return list(active.values())

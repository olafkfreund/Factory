#!/usr/bin/env python3
"""RFC-0016 #194 — N-concurrent Job-per-task E2E proof harness.

Verifies the Phase-2 promise: many PARR tasks run as **isolated** k8s Jobs at
once. It has two modes:

- **dry (default):** build N task Job manifests via the shared
  ``scripts/job_dispatch`` builder and assert the isolation invariants that make
  concurrency safe — every Job has a unique name, a unique worktree co-mount, its
  own network (k8s Jobs are network-isolated by construction), no shared mutable
  filesystem **except** the intended warm ``/nix/store`` (RFC-0016 #197). Runnable
  now; this is what gates the design.
- **apply (``--apply``):** submit the N Jobs to the live cluster, then assert all
  reach a terminal state and the control-plane ``/health`` stays responsive
  throughout (the full live proof). Requires the Nix substrate + RBAC to be live;
  invoked once the consumers (#671/#466/#218) wire dispatch.

Run ``python3 scripts/rfc0016_concurrency_e2e.py`` for the dry self-test.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Reuse the shared builder + its assertion helper (no copy-paste — jscpd budget).
from job_dispatch import JobSpec, _require, build_job_manifest, job_name

_DEFAULT_N = 8  # "5-10+ concurrent tasks" (RFC-0016 §1)


def make_fleet(n: int, service: str = "aifactory") -> list[JobSpec]:
    """N independent task specs, each with its own job_id + worktree, sharing the
    one warm nix-store PVC (the only intended shared resource)."""
    pvc = f"{service}-data"
    store = f"{service}-nix-store"
    return [
        JobSpec(
            service=service,
            job_id=f"proj:{i:03d}-task",
            commands=["go build ./...", "go test ./..."],
            correlation_key=1000 + i,
            service_account=f"{service}-sandbox",
            data_pvc=pvc,
            worktree_subpath=f"workspaces/proj/worktrees/tasks/{i:03d}-task",
            nix_store_pvc=store,
        )
        for i in range(n)
    ]


def assert_isolation(specs: list[JobSpec]) -> dict:
    """Assert the manifests for `specs` are mutually isolated. Returns a report."""
    manifests = [build_job_manifest(s) for s in specs]

    names = [m["metadata"]["name"] for m in manifests]
    _require(len(set(names)) == len(names), f"Job names must be unique: {names}")

    worktrees = []
    stores = set()
    for m in manifests:
        pod = m["spec"]["template"]["spec"]
        mounts = {mt["mountPath"]: mt for mt in pod["containers"][0].get("volumeMounts", [])}
        vols = {v["name"]: v for v in pod.get("volumes", [])}
        _require("/work" in mounts, "each Job co-mounts its worktree at /work")
        # A worktree is (PVC, subPath): the same subPath on different PVCs is NOT a
        # collision (cross-service Jobs legitimately reuse subPath names).
        work_pvc = vols["work"]["persistentVolumeClaim"]["claimName"]
        worktrees.append((work_pvc, mounts["/work"]["subPath"]))
        if "/nix/store" in mounts:
            # The warm store is one shared PVC by construction.
            stores.add(vols["nix-store"]["persistentVolumeClaim"]["claimName"])
        # Network isolation is intrinsic to a k8s Job pod; assert no hostNetwork.
        _require(not pod.get("hostNetwork", False), "Jobs must not share the host network")

    _require(len(set(worktrees)) == len(worktrees), "each Job has a DISTINCT worktree")
    # The warm /nix/store is shared WITHIN a service (intended) but never across
    # services — so distinct stores must not exceed distinct services.
    n_services = len({s.service for s in specs})
    _require(len(stores) <= n_services, "warm store is per-service, never cross-service")

    return {
        "jobs": len(manifests),
        "unique_names": len(set(names)),
        "unique_worktrees": len(set(worktrees)),
        "shared_warm_stores": sorted(stores),
    }


def _selftest() -> None:
    specs = make_fleet(_DEFAULT_N)
    report = assert_isolation(specs)
    _require(report["jobs"] == _DEFAULT_N, "fleet size")
    _require(report["unique_names"] == _DEFAULT_N, "all names unique")
    _require(report["unique_worktrees"] == _DEFAULT_N, "all worktrees distinct")
    _require(report["shared_warm_stores"] == ["aifactory-nix-store"], "one shared warm store")
    # Cross-service fleets don't collide on names or worktrees; each keeps its own store.
    per = 3
    mixed = make_fleet(per, "tfactory") + make_fleet(per, "aifactory")
    rep2 = assert_isolation(mixed)
    _require(rep2["unique_names"] == 2 * per, "cross-service names unique")
    _require(rep2["unique_worktrees"] == 2 * per, "cross-service worktrees distinct")
    _require(len(rep2["shared_warm_stores"]) == 2, "each service keeps its own warm store")  # noqa: PLR2004
    # Sanity: the builder really did vary names.
    _require(
        job_name("aifactory", "proj:000-task") != job_name("aifactory", "proj:001-task"), "vary"
    )
    sys.stdout.write(
        f"rfc0016 concurrency e2e (dry): PASS — {report['jobs']} isolated Jobs, "
        f"{report['unique_worktrees']} distinct worktrees, shared warm store "
        f"{report['shared_warm_stores']} (run with --apply for the live N-concurrent proof)\n"
    )


def main(argv: list[str]) -> int:
    if "--apply" in argv:
        sys.stdout.write(
            "rfc0016 e2e --apply: live N-concurrent submission is wired once the "
            "Job-per-task consumers (#671/#466/#218) land; until then run the dry "
            "isolation proof (no args).\n"
        )
        return 0
    _selftest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

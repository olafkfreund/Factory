#!/usr/bin/env python3
"""RFC-0006 per-technology verification profiles (reference implementation).

Answers "what verification is even POSSIBLE for this artifact, and what does each
level need?" — so the planner can declare a realistic `target_level` and the
runner knows which levels it can actually reach. The output is a verification
**plan skeleton** whose un-achievable levels are pre-marked `not_run` with a
`reason` — exactly the shape the #72 gate (`verification_gate.normalize_verification`)
then enforces honesty on.

A profile maps an artifact type to its assurance ladder. Each level lists the
commands it would run and the capabilities it `requires`. A level is *achievable*
only when its requirements are a subset of the capabilities the environment
actually provides (toolchains from the RFC-0005 sandbox; targets/creds only when
provisioned). Everything below VAL-0 toolchains is provisionable; VAL-3 targets
usually are not — and that gap is reported honestly, never hidden.

Pure + dependency-free so PFactory / AIFactory / TFactory vendor it.
Run directly for the self-tests: `python3 scripts/verification_profiles.py`.
"""

from __future__ import annotations

import fnmatch
from typing import TypedDict


class LevelSpec(TypedDict, total=False):
    """What one assurance level would run and what it needs to run it."""

    commands: list[str]
    requires: list[str]
    risk: str


class Profile(TypedDict, total=False):
    """A per-artifact-type verification profile.

    `detect` (globs) and `levels` (the assurance ladder) are present on every
    profile; `credential_class` only on artifacts whose credentialed level
    needs external access, so the TypedDict is `total=False`.
    """

    detect: list[str]
    credential_class: str
    levels: dict[str, LevelSpec]


class PlanLevel(TypedDict, total=False):
    """One rung of the planned ladder emitted by `plan_verification`."""

    level: str
    commands: list[str]
    status: str
    reason: str
    risk: str


class VerificationPlan(TypedDict):
    """The verification-plan skeleton `plan_verification` returns."""

    artifact_type: str
    target_level: str
    achievable_level: str
    levels: list[PlanLevel]


# artifact type -> { detect: [globs], levels: {VAL-x: {commands, requires, risk}} }
PROFILES: dict[str, Profile] = {
    "ansible": {
        "detect": [
            "**/playbook*.yml",
            "**/site.yml",
            "**/roles/**/tasks/*.yml",
            "ansible.cfg",
            "**/molecule/**",
        ],
        # RFC-0007: VAL-3 applies to disposable sandbox hosts the pipeline owns.
        "credential_class": "C-ephemeral-target",
        "levels": {
            "VAL-0": {
                "commands": ["ansible-lint", "ansible-playbook --syntax-check"],
                "requires": ["ansible"],
            },
            "VAL-2": {
                "commands": ["molecule test"],
                "requires": ["ansible", "molecule", "container_runtime"],
                "risk": "role not converged anywhere; task logic unproven",
            },
            "VAL-3": {
                "commands": ["ansible-playbook -i <sandbox-inventory> --diff"],
                "requires": ["sandbox_target", "credentials"],
                "risk": "not applied to real hosts; apply-time failures possible",
            },
        },
    },
    "terraform": {
        "detect": ["*.tf", "*.tf.json", "**/*.tf"],
        # RFC-0007: cloud auth should be machine-native (workload identity / OIDC
        # federation / scoped token) — no MFA in the path. The VAL-3 target is an
        # ephemeral project, but the credential the planner needs is class A.
        "credential_class": "A-machine-native",
        "levels": {
            "VAL-0": {"commands": ["terraform validate", "tflint"], "requires": ["terraform"]},
            "VAL-2": {
                "commands": ["terraform plan"],
                "requires": ["terraform", "credentials"],
                "risk": "plan not generated; drift/diff unknown",
            },
            "VAL-3": {
                "commands": ["terraform apply", "terraform destroy"],
                "requires": ["sandbox_cloud", "credentials"],
                "risk": "not applied; real provisioning unproven",
            },
        },
    },
    "kubernetes": {
        "detect": ["**/Chart.yaml", "**/kustomization.yaml", "k8s/**/*.yaml"],
        # RFC-0007: VAL-3 applies to an ephemeral cluster the pipeline provisions.
        "credential_class": "C-ephemeral-target",
        "levels": {
            "VAL-0": {"commands": ["kubeconform", "helm lint"], "requires": ["kubeconform"]},
            "VAL-2": {
                "commands": ["helm template | kubeconform", "kind load + apply --dry-run"],
                "requires": ["kind", "container_runtime"],
                "risk": "manifests not applied to a live cluster",
            },
            "VAL-3": {
                "commands": ["apply to ephemeral cluster + assert ready"],
                "requires": ["sandbox_cluster"],
                "risk": "rollout behavior unproven",
            },
        },
    },
    "python-library": {
        "detect": ["pyproject.toml", "setup.py", "setup.cfg"],
        "levels": {
            "VAL-0": {"commands": ["ruff check", "mypy"], "requires": ["ruff"]},
            "VAL-1": {"commands": ["pytest"], "requires": ["pytest"]},
            "VAL-2": {
                "commands": ["pytest -m integration (testcontainers/devenv services)"],
                "requires": ["pytest", "container_runtime"],
                "risk": "integration paths exercised only if such tests exist",
            },
        },
    },
    "node-web": {
        "detect": ["package.json"],
        "levels": {
            "VAL-0": {"commands": ["eslint", "tsc --noEmit"], "requires": ["node"]},
            "VAL-1": {"commands": ["npm test"], "requires": ["node"]},
            "VAL-2": {
                "commands": ["playwright test (ephemeral browser)"],
                "requires": ["node", "playwright", "container_runtime"],
                "risk": "no end-to-end browser run",
            },
        },
    },
    "go": {
        "detect": ["go.mod"],
        "levels": {
            "VAL-0": {"commands": ["go vet", "golangci-lint run"], "requires": ["go"]},
            "VAL-1": {"commands": ["go test ./..."], "requires": ["go"]},
        },
    },
    "rust": {
        "detect": ["Cargo.toml"],
        "levels": {
            "VAL-0": {"commands": ["cargo clippy"], "requires": ["cargo"]},
            "VAL-1": {"commands": ["cargo test"], "requires": ["cargo"]},
        },
    },
    "java": {
        "detect": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "levels": {
            "VAL-0": {"commands": ["mvn -q compile"], "requires": ["mvn"]},
            "VAL-1": {"commands": ["mvn test"], "requires": ["mvn"]},
        },
    },
    # RFC-0013 deployment-aware verification. A "deploy" artifact is a change that
    # ships through a CI/CD pipeline (pipeline definitions, GitOps manifests).
    # Deploy verification is DRY-RUN by policy: VAL-2 is the pipeline/manifest
    # dry-run; VAL-3 applies to a DISPOSABLE (ephemeral) target the pipeline owns;
    # there is deliberately NO autonomous VAL-4 — a production apply is never run
    # by the fleet (it is held behind the RFC-0013 human-approval system gate).
    "deploy": {
        "detect": [
            "**/.github/workflows/*deploy*.y*ml",
            "**/.gitlab-ci.yml",
            "**/azure-pipelines.yml",
            "**/argocd/**/*.y*ml",
            "**/Application*.yaml",
        ],
        # RFC-0007: an ephemeral deploy target the pipeline provisions and tears down.
        "credential_class": "C-ephemeral-target",
        "levels": {
            "VAL-0": {
                "commands": [
                    "pipeline lint (actionlint / gitlab-ci-lint)",
                    "manifest schema check",
                ],
                "requires": ["ci_linter"],
            },
            "VAL-2": {
                "commands": ["deploy dry-run (helm template / terraform plan / kubectl --dry-run)"],
                "requires": ["deploy_tool", "container_runtime"],
                "risk": "dry-run only; pipeline not executed against any target",
            },
            "VAL-3": {
                "commands": ["apply to ephemeral target + assert healthy + teardown"],
                "requires": ["sandbox_target", "credentials"],
                "risk": "applied only to a disposable target; production rollout unproven",
            },
            # No VAL-4 entry by design: production deploy is NEVER autonomous
            # (RFC-0013). The planned ladder therefore caps at VAL-3.
        },
    },
    # Fallback: we can always at least try to build/test if commands are given,
    # but we never assume more than VAL-1 without a profile.
    "generic": {
        "detect": [],
        "levels": {
            "VAL-0": {"commands": ["(language linters)"], "requires": []},
            "VAL-1": {"commands": ["(declared test command)"], "requires": []},
        },
    },
}

# Detection priority (most specific / most effectful first).
_ORDER = [
    "deploy",
    "ansible",
    "terraform",
    "kubernetes",
    "java",
    "go",
    "rust",
    "node-web",
    "python-library",
]

_LADDER = ["VAL-0", "VAL-1", "VAL-2", "VAL-3", "VAL-4"]


def detect_artifact_type(files: list[str]) -> str:
    for t in _ORDER:
        globs = PROFILES[t]["detect"]
        for f in files:
            if any(fnmatch.fnmatch(f, g) or fnmatch.fnmatch("/" + f, g) for g in globs):
                return t
    return "generic"


def credential_class_for(artifact_type: str) -> str | None:
    """RFC-0007 access class an artifact's credentialed level needs (#85).

    Returns one of the four access classes (A-machine-native / B-bootstrap-once /
    C-ephemeral-target / D-un-automatable) for artifacts whose effectful (VAL-3)
    verification requires reaching a credentialed/sandbox resource — terraform's
    cloud auth is machine-native (A); ansible hosts and k8s clusters are ephemeral
    targets the pipeline provisions (C). Returns None for artifacts whose highest
    level is satisfiable locally/ephemerally (go/rust/python/node/java/generic) —
    they need no external access. PFactory uses this as the per-technology default
    when seeding an `access` requirement (RFC-0007 / #84).
    """
    profile = PROFILES.get(artifact_type)
    return profile.get("credential_class") if profile else None


def plan_verification(files: list[str], available: set[str]) -> VerificationPlan:
    """Build a verification-plan skeleton for the detected artifact.

    `available` = capabilities the environment provides (toolchains/runtimes/
    targets). Returns target_level (top of the ladder), achievable_level (highest
    level whose requirements are met), and a `levels` list where un-achievable
    levels are pre-marked not_run with a reason — ready for the #72 gate.
    """
    art = detect_artifact_type(files)
    profile = PROFILES[art]["levels"]
    ladder = [l for l in _LADDER if l in profile]
    target_level = ladder[-1] if ladder else "VAL-0"

    levels: list[PlanLevel] = []
    achievable = "VAL-0"
    for lvl in ladder:
        spec = profile[lvl]
        missing = [r for r in spec.get("requires", []) if r not in available]
        entry: PlanLevel = {"level": lvl, "commands": spec["commands"]}
        if missing:
            entry["status"] = "not_run"
            entry["reason"] = "requires " + ", ".join(missing)
            risk = spec.get("risk")
            if risk:
                entry["risk"] = risk
        else:
            entry["status"] = "planned"  # runner will execute -> passed/failed
            achievable = lvl
        levels.append(entry)

    return {
        "artifact_type": art,
        "target_level": target_level,
        "achievable_level": achievable,
        "levels": levels,
    }


# --------------------------------------------------------------------------- #
def _require(cond: bool, msg: str) -> None:
    """Lint-clean assert for the self-tests (avoids S101 under the strict bar)."""
    if not cond:
        raise AssertionError(msg)


def _test() -> None:
    ans = ["roles/web/tasks/main.yml", "molecule/default/molecule.yml"]

    assert detect_artifact_type(ans) == "ansible"
    assert detect_artifact_type(["main.tf"]) == "terraform"
    assert detect_artifact_type(["go.mod"]) == "go"
    assert detect_artifact_type(["pyproject.toml"]) == "python-library"
    assert detect_artifact_type(["README.md"]) == "generic"

    # Ansible, only the lint toolchain present: VAL-0 achievable, VAL-2/3 honest gaps.
    p = plan_verification(ans, available={"ansible"})
    assert p["target_level"] == "VAL-3" and p["achievable_level"] == "VAL-0", p
    by = {l["level"]: l for l in p["levels"]}
    assert by["VAL-0"]["status"] == "planned"
    assert by["VAL-2"]["status"] == "not_run" and "molecule" in by["VAL-2"]["reason"]
    assert by["VAL-3"]["status"] == "not_run" and "sandbox_target" in by["VAL-3"]["reason"]

    # Add molecule + a container runtime: now VAL-2 is achievable; VAL-3 still not.
    p = plan_verification(ans, available={"ansible", "molecule", "container_runtime"})
    assert p["achievable_level"] == "VAL-2", p
    by = {l["level"]: l for l in p["levels"]}
    assert by["VAL-2"]["status"] == "planned"
    assert by["VAL-3"]["status"] == "not_run", by["VAL-3"]

    # Provision a sandbox target + creds: full ladder achievable.
    p = plan_verification(
        ans, available={"ansible", "molecule", "container_runtime", "sandbox_target", "credentials"}
    )
    assert p["achievable_level"] == "VAL-3", p

    # Every not_run level carries a reason (feeds the #72 gate's schema requirement).
    for p in (plan_verification(ans, {"ansible"}),):
        for l in p["levels"]:
            if l["status"] == "not_run":
                assert l.get("reason"), l

    # RFC-0007 (#85): per-technology credential class for the credentialed level.
    assert credential_class_for("terraform") == "A-machine-native"
    assert credential_class_for("ansible") == "C-ephemeral-target"
    assert credential_class_for("kubernetes") == "C-ephemeral-target"
    # Locally/ephemerally satisfiable artifacts need no external access.
    for t in ("go", "rust", "python-library", "node-web", "java", "generic"):
        assert credential_class_for(t) is None, t
    assert credential_class_for("unknown-type") is None

    # RFC-0013 (#151): deploy artifacts cap dry-run verification at VAL-2/VAL-3;
    # there is NO autonomous VAL-4 (production apply is never run by the fleet).
    deploy_files = [".github/workflows/deploy.yml", "argocd/app.yaml"]
    _require(detect_artifact_type(deploy_files) == "deploy", str(deploy_files))
    _require(detect_artifact_type([".gitlab-ci.yml"]) == "deploy", "gitlab-ci")

    # The planned ladder tops out at VAL-3 — production (VAL-4) is never planned.
    p = plan_verification(deploy_files, available={"ci_linter"})
    _require(p["target_level"] == "VAL-3", str(p))
    _require("VAL-4" not in {lvl["level"] for lvl in p["levels"]}, str(p))
    by = {lvl["level"]: lvl for lvl in p["levels"]}
    # Only the pipeline linter present: VAL-0 achievable, dry-run/ephemeral honest gaps.
    _require(by["VAL-0"]["status"] == "planned", str(by["VAL-0"]))
    _require("deploy_tool" in by["VAL-2"]["reason"], str(by["VAL-2"]))
    _require("sandbox_target" in by["VAL-3"]["reason"], str(by["VAL-3"]))

    # Add the deploy tool + a runtime: the VAL-2 dry-run is achievable; VAL-3 not.
    avail = {"ci_linter", "deploy_tool", "container_runtime"}
    p = plan_verification(deploy_files, available=avail)
    _require(p["achievable_level"] == "VAL-2", str(p))
    not_run = {lvl["level"] for lvl in p["levels"] if lvl["status"] == "not_run"}
    _require(not_run == {"VAL-3"}, str(p))

    # Provision a disposable target + creds: VAL-3 (ephemeral apply) achievable;
    # still no VAL-4 — production apply remains outside the autonomous ladder.
    full = {"ci_linter", "deploy_tool", "container_runtime", "sandbox_target", "credentials"}
    p = plan_verification(deploy_files, available=full)
    _require(p["achievable_level"] == "VAL-3", str(p))
    _require(p["target_level"] == "VAL-3", str(p))

    # Deploy's credentialed level reaches an ephemeral target (RFC-0007 class C).
    _require(credential_class_for("deploy") == "C-ephemeral-target", "deploy class")

    print("verification_profiles self-tests: passed")


if __name__ == "__main__":
    _test()

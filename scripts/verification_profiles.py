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

# artifact type -> { detect: [globs], levels: {VAL-x: {commands, requires, risk}} }
PROFILES: dict[str, dict] = {
    "ansible": {
        "detect": ["**/playbook*.yml", "**/site.yml", "**/roles/**/tasks/*.yml",
                   "ansible.cfg", "**/molecule/**"],
        "levels": {
            "VAL-0": {"commands": ["ansible-lint", "ansible-playbook --syntax-check"],
                      "requires": ["ansible"]},
            "VAL-2": {"commands": ["molecule test"],
                      "requires": ["ansible", "molecule", "container_runtime"],
                      "risk": "role not converged anywhere; task logic unproven"},
            "VAL-3": {"commands": ["ansible-playbook -i <sandbox-inventory> --diff"],
                      "requires": ["sandbox_target", "credentials"],
                      "risk": "not applied to real hosts; apply-time failures possible"},
        },
    },
    "terraform": {
        "detect": ["*.tf", "*.tf.json", "**/*.tf"],
        "levels": {
            "VAL-0": {"commands": ["terraform validate", "tflint"],
                      "requires": ["terraform"]},
            "VAL-2": {"commands": ["terraform plan"],
                      "requires": ["terraform", "credentials"],
                      "risk": "plan not generated; drift/diff unknown"},
            "VAL-3": {"commands": ["terraform apply", "terraform destroy"],
                      "requires": ["sandbox_cloud", "credentials"],
                      "risk": "not applied; real provisioning unproven"},
        },
    },
    "kubernetes": {
        "detect": ["**/Chart.yaml", "**/kustomization.yaml", "k8s/**/*.yaml"],
        "levels": {
            "VAL-0": {"commands": ["kubeconform", "helm lint"], "requires": ["kubeconform"]},
            "VAL-2": {"commands": ["helm template | kubeconform", "kind load + apply --dry-run"],
                      "requires": ["kind", "container_runtime"],
                      "risk": "manifests not applied to a live cluster"},
            "VAL-3": {"commands": ["apply to ephemeral cluster + assert ready"],
                      "requires": ["sandbox_cluster"],
                      "risk": "rollout behavior unproven"},
        },
    },
    "python-library": {
        "detect": ["pyproject.toml", "setup.py", "setup.cfg"],
        "levels": {
            "VAL-0": {"commands": ["ruff check", "mypy"], "requires": ["ruff"]},
            "VAL-1": {"commands": ["pytest"], "requires": ["pytest"]},
            "VAL-2": {"commands": ["pytest -m integration (testcontainers/devenv services)"],
                      "requires": ["pytest", "container_runtime"],
                      "risk": "integration paths exercised only if such tests exist"},
        },
    },
    "node-web": {
        "detect": ["package.json"],
        "levels": {
            "VAL-0": {"commands": ["eslint", "tsc --noEmit"], "requires": ["node"]},
            "VAL-1": {"commands": ["npm test"], "requires": ["node"]},
            "VAL-2": {"commands": ["playwright test (ephemeral browser)"],
                      "requires": ["node", "playwright", "container_runtime"],
                      "risk": "no end-to-end browser run"},
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
_ORDER = ["ansible", "terraform", "kubernetes", "java", "go", "rust",
          "node-web", "python-library"]

_LADDER = ["VAL-0", "VAL-1", "VAL-2", "VAL-3", "VAL-4"]


def detect_artifact_type(files: list[str]) -> str:
    for t in _ORDER:
        globs = PROFILES[t]["detect"]
        for f in files:
            if any(fnmatch.fnmatch(f, g) or fnmatch.fnmatch("/" + f, g) for g in globs):
                return t
    return "generic"


def plan_verification(files: list[str], available: set[str]) -> dict:
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

    levels: list[dict] = []
    achievable = "VAL-0"
    for lvl in ladder:
        spec = profile[lvl]
        missing = [r for r in spec.get("requires", []) if r not in available]
        entry = {"level": lvl, "commands": spec["commands"]}
        if missing:
            entry["status"] = "not_run"
            entry["reason"] = "requires " + ", ".join(missing)
            if spec.get("risk"):
                entry["risk"] = spec["risk"]
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
    p = plan_verification(ans, available={"ansible", "molecule", "container_runtime",
                                          "sandbox_target", "credentials"})
    assert p["achievable_level"] == "VAL-3", p

    # Every not_run level carries a reason (feeds the #72 gate's schema requirement).
    for p in (plan_verification(ans, {"ansible"}),):
        for l in p["levels"]:
            if l["status"] == "not_run":
                assert l.get("reason"), l

    print("verification_profiles self-tests: passed")


if __name__ == "__main__":
    _test()

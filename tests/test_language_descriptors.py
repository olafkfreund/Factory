"""The declarative language descriptors and their provisioner wiring (RFC-0005).

Two subjects, deliberately in one module:

1. The REAL descriptors under contracts/languages/ load and say what they must.
   The load-bearing schema rule — ``available: false`` REQUIRES a reason — is
   asserted against the shipped files, not only against synthetic fixtures, so
   a descriptor edit that drops a reason fails here before it ships.

2. The provisioner actually READS them. The negative control unwires the
   descriptor path and demands the refusal: a descriptor that is never read and
   a descriptor that reads correctly must not produce identical results
   (the pass-shaped empty measurement this fleet keeps producing).

The lanes themselves were proven by RUNNING them, not by these tests: a minimal
SPM package and a minimal Gradle module passed (and, mutated, failed) inside
``nix develop`` of the GENERATED flakes on x86_64-linux, 2026-09-03. What these
tests pin is the machinery that got them there.
"""

from __future__ import annotations

import nix_provisioner
import pytest
from language_descriptors import (
    DescriptorError,
    load_languages,
    resolve_language,
)
from nix_provisioner import ProvisionError, generate_flake


class TestShippedDescriptors:
    """The real contracts/languages/*.yaml, as vendored."""

    def test_swift_and_kotlin_load(self) -> None:
        langs = load_languages()
        assert "swift" in langs and "kotlin" in langs

    def test_swift_unit_lane_is_runnable(self) -> None:
        lane = load_languages()["swift"].lane("unit")
        assert lane is not None and lane.available
        assert lane.command == "swift test"
        assert lane.tool == "xctest"
        # The LinuxMain constraint is recorded, not silently assumed
        # (NixOS/nixpkgs#379859: no libIndexStore.so, no automatic discovery).
        assert "LinuxMain" in lane.notes

    def test_swift_ui_lane_is_honestly_unavailable(self) -> None:
        """The whole point: unavailability is machine-readable, with a reason.

        The ui lane must NEVER be reportable as passed — structurally, an
        unavailable lane carries no command, so there is nothing to run and
        nothing whose exit code could be mistaken for a verdict.
        """
        swift = load_languages()["swift"]
        lane = swift.lane("ui")
        assert lane is not None and not lane.available
        assert "macOS" in lane.reason
        assert swift.unavailable_reason("ui") == lane.reason
        assert lane.command == "" and lane.tool == ""

    def test_every_unavailable_lane_fleet_wide_carries_a_reason(self) -> None:
        for name, descriptor in load_languages().items():
            for key, lane in descriptor.lanes.items():
                if not lane.available:
                    assert lane.reason, f"{name}.{key}: unavailable without a reason"
                else:
                    assert lane.command and lane.tool, f"{name}.{key}: runnable without a command"

    def test_kotlin_unit_and_mutation_are_runnable(self) -> None:
        kotlin = load_languages()["kotlin"]
        unit = kotlin.lane("unit")
        mutation = kotlin.lane("mutation")
        assert unit is not None and unit.available and unit.command.startswith("gradle test")
        assert mutation is not None and mutation.available and mutation.tool == "pit"

    def test_alias_resolution(self) -> None:
        swift = resolve_language("spm")
        assert swift is not None and swift.name == "swift"
        assert resolve_language("elixir") is None


class TestSchemaRefusals:
    """Descriptors that lie or omit are refused at load, loudly."""

    def test_unavailable_without_reason_refused(self, tmp_path) -> None:
        (tmp_path / "bad.yaml").write_text(
            "name: bad\naliases: [bad]\nnix: {packages: [x]}\nlanes:\n  unit: {available: false}\n"
        )
        with pytest.raises(DescriptorError, match="REQUIRES a non-empty reason"):
            load_languages(tmp_path)

    def test_available_without_command_refused(self, tmp_path) -> None:
        (tmp_path / "bad.yaml").write_text(
            "name: bad\naliases: [bad]\nnix: {packages: [x]}\n"
            "lanes:\n  unit: {available: true, tool: t}\n"
        )
        with pytest.raises(DescriptorError, match="must name its command"):
            load_languages(tmp_path)

    def test_empty_directory_is_a_broken_vendoring_not_a_clean_registry(self, tmp_path) -> None:
        with pytest.raises(DescriptorError, match=r"no \*\.yaml descriptors"):
            load_languages(tmp_path)


class TestProvisionerReadsDescriptors:
    """Site 5: generate_flake extends its tables from the descriptors."""

    def test_swift_flake_has_toolchain_and_corelibs_env(self) -> None:
        flake = generate_flake({"language": "swift", "verify_commands": ["swift test"]})
        assert "pkgs.swiftpm" in flake
        assert "pkgs.swiftPackages.XCTest" in flake
        # Without the corelibs on LD_LIBRARY_PATH swiftpm dies at manifest
        # compile ("libdispatch.so: cannot open shared object file") — proven
        # in-shell 2026-09-03, before this line existed.
        assert 'LD_LIBRARY_PATH = "${pkgs.swiftPackages.Dispatch}/lib' in flake
        assert "withPackages" not in flake

    def test_kotlin_flake_has_toolchain(self) -> None:
        flake = generate_flake(
            {"language": "kotlin", "verify_commands": ["gradle test --no-daemon"]}
        )
        for attr in ("pkgs.kotlin", "pkgs.gradle", "pkgs.jdk21"):
            assert attr in flake, flake

    def test_builtin_languages_keep_their_own_resolvers(self) -> None:
        """The descriptor path must not shadow the version-aware builtins."""
        flake = generate_flake(
            {"language": "go", "toolchain": {"go": "1.25"}, "verify_commands": ["go test ./..."]}
        )
        assert "pkgs.go_1_25" in flake

    def test_negative_control_unwired_descriptors_refuse(self, monkeypatch) -> None:
        """Unwire the call site; the same manifest must go RED.

        A generator that still provisions swift with the descriptor path
        removed would mean these descriptors are decoration, and every
        assertion above a pass-shaped empty measurement.
        """
        monkeypatch.setattr(nix_provisioner, "_resolve_descriptor", None)
        with pytest.raises(ProvisionError, match=r"unsupported environment\.language 'swift'"):
            generate_flake({"language": "swift", "verify_commands": ["swift test"]})

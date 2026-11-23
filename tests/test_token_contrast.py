"""Verify Factory UI token contrast with the real palette and regressions."""

from pathlib import Path

import check_token_contrast as gate
import pytest


def test_canonical_token_contrast() -> None:
    assert gate.check(gate.TOKENS.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("replacement", "pair"),
    [
        (("text-muted", "0.352 0.008 65"), "--f-text-muted on --f-surface-3"),
        (("meet", "0.240 0.004 80"), "--f-meet on --f-bg"),
        (("border-strong", "0.352 0.008 65"), "--f-border-strong on --f-surface-3"),
        (("info", "0.220 0.004 80"), "--f-on-accent on --f-info"),
    ],
)
def test_weakened_dark_token_fails_without_changing_hex_comments(
    replacement: tuple[str, str],
    pair: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    token, color = replacement
    css = gate.TOKENS.read_text(encoding="utf-8")
    prefix = f"--f-{token}: oklch("
    before, _, dark_value = css.rpartition(prefix)
    _, _, after = dark_value.partition(")")
    weakened = tmp_path / "tokens.css"
    weakened.write_text(f"{before}{prefix}{color}){after}", encoding="utf-8")
    monkeypatch.setattr(gate, "TOKENS", weakened)
    assert gate.main() == 1
    assert f"dark: {pair} has contrast 1.000:1" in capsys.readouterr().err


def test_missing_mode_fails() -> None:
    css = gate.TOKENS.read_text(encoding="utf-8")
    assert gate.check(css.replace(".dark {", ".missing {", 1)) == [".dark: missing --f-bg"]


def test_status_text_on_dark_surface_is_checked() -> None:
    css = gate.TOKENS.read_text(encoding="utf-8")
    before, marker, after = css.rpartition("--f-danger: oklch(0.745")
    assert marker
    weakened = f"{before}--f-danger: oklch(0.725{after}"
    assert any("dark: --f-danger on --f-surface-3" in p for p in gate.check(weakened))


@pytest.mark.parametrize("portal", [None, *gate._ACCENTS])
def test_active_accent_must_reference_checked_accent(portal: str | None) -> None:
    css = gate.TOKENS.read_text(encoding="utf-8")
    target = "build" if portal is None else portal
    selector = ":root" if portal is None else f':root[data-portal="{portal}"]'
    original = f"--f-accent: var(--f-{target});"
    if portal is None:
        broken = css.replace(original, "--f-accent: var(--f-bg);", 1)
    else:
        broken = css.replace(
            f"{selector} {{\n  {original}",
            f"{selector} {{\n  --f-accent: var(--f-bg);",
        )
    assert f"{selector}: --f-accent must reference a checked accent token" in gate.check(broken)

#!/usr/bin/env python3
"""Check WCAG contrast pairs in the canonical Factory UI token stylesheet."""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

TOKENS = Path(__file__).resolve().parents[1] / "shared/factory-ui/tokens.css"
_SURFACES = ("bg", "surface-1", "surface-2", "surface-3")
_TEXT = ("text", "text-secondary", "text-muted")
_ACCENTS = ("plan", "build", "test", "cockpit", "meet")
_STATUSES = ("success", "warning", "danger", "info")


def _relative_luminance(value: str) -> float:
    match = re.fullmatch(r"oklch\(([^()]*)\)", value)
    if match is None:
        raise ValueError("expected oklch(L C H)")
    lightness, chroma, hue = map(float, match[1].split())
    if not (0 <= lightness <= 1 and chroma >= 0 and math.isfinite(chroma + hue)):
        raise ValueError("invalid OKLCH coordinates")

    # CSS Color 4 conversion to linear sRGB using Ottosson's combined matrices.
    angle = math.radians(hue)
    a, b = chroma * math.cos(angle), chroma * math.sin(angle)
    long = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short,
    )
    # shortcut: clip to sRGB, use CSS gamut mapping if the palette moves outside sRGB.
    return sum(
        weight * min(1.0, max(0.0, channel))
        for weight, channel in zip((0.2126, 0.7152, 0.0722), rgb, strict=True)
    )


def _declarations(css: str, selector: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for block in re.findall(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", css):
        declarations.update(re.findall(r"--f-([\w-]+)\s*:\s*([^;]+)", block))
    return declarations


def _mode_luminances(css: str, selector: str) -> dict[str, float]:
    declarations = _declarations(css, selector)
    luminances = {}
    for name in (*_SURFACES, *_TEXT, *_ACCENTS, *_STATUSES, "border-strong", "on-accent"):
        if name not in declarations:
            raise ValueError(f"{selector}: missing --f-{name}")
        try:
            luminances[name] = _relative_luminance(declarations[name].strip())
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"{selector}: invalid --f-{name}: {exc}") from exc
    return luminances


def check(css: str) -> list[str]:
    """Return missing, invalid, or low-contrast token diagnostics."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    pairs = [
        (foreground, surface, 4.5)
        for foreground in (*_TEXT, *_ACCENTS, *_STATUSES)
        for surface in _SURFACES
    ]
    pairs.extend(("border-strong", surface, 3.0) for surface in _SURFACES)
    pairs.extend(("on-accent", fill, 4.5) for fill in (*_ACCENTS, *_STATUSES))
    problems = []
    for selector in (":root", *(f':root[data-portal="{name}"]' for name in _ACCENTS)):
        alias = _declarations(css, selector).get("accent", "").strip()
        if alias not in {f"var(--f-{name})" for name in _ACCENTS}:
            problems.append(f"{selector}: --f-accent must reference a checked accent token")
    for mode, selector in (("light", ":root"), ("dark", ".dark")):
        try:
            luminances = _mode_luminances(css, selector)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        for foreground, background, minimum in pairs:
            darker, lighter = sorted((luminances[foreground], luminances[background]))
            ratio = (lighter + 0.05) / (darker + 0.05)
            if ratio < minimum:
                problems.append(
                    f"{mode}: --f-{foreground} on --f-{background} has contrast "
                    f"{ratio:.3f}:1, minimum {minimum:g}:1"
                )
    return problems


def main() -> int:
    try:
        problems = check(TOKENS.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        print(f"Factory UI token contrast: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    if problems:
        print("\n".join(problems), file=sys.stderr)  # noqa: T201
        return 1
    print("Factory UI token contrast passed in light and dark modes.")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

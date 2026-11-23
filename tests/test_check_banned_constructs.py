"""Coverage of the portal small-text rule in the banned constructs gate."""

from pathlib import Path

import check_banned_constructs as gate
import pytest


@pytest.mark.parametrize(
    ("relative", "source", "violation"),
    [
        ("apps/frontend-web/src/App.tsx", 'className="hover:text-[11px]/4"', "text-[11px]"),
        ("apps/frontend-web/src/App.tsx", 'className="text-[.749rem]!"', "text-[.749rem]"),
        ("apps/frontend-web/src/ui.css", ".label { font-size: 11.9px }", "font-size: 11.9px"),
        ("apps/frontend-web/src/ui.css", ".label { FONT-SIZE: .7REM }", "FONT-SIZE: .7REM"),
        ("web/public/index.html", '<span class="text-[10px]">', "text-[10px]"),
        ("web/public/ui.css", ".label { font-size: 0.625rem }", "font-size: 0.625rem"),
    ],
)
def test_portal_small_text_is_reported(
    tmp_path: Path, relative: str, source: str, violation: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(f"\n{source}\n", encoding="utf-8")
    assert gate.check(tmp_path, None) == [f"{relative}:2: small-text — {violation}"]


def test_legible_text_comments_and_other_paths_are_ignored(tmp_path: Path) -> None:
    for relative, source in {
        "apps/frontend-web/src/App.tsx": 'className="text-[12px] text-[0.75rem] text-[1rem]"',
        "web/style.css": "/* font-size: 10px */ .a { font-size: 12px; font-size: 0.75rem }",
        "apps/backend/example.ts": 'const sample = "text-[11px]"',
        "docs/example.css": ".a { font-size: 11px }",
        "web/vendor/example.css": ".a { font-size: 11px }",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    assert gate.check(tmp_path, None) == []


def test_small_text_uses_the_existing_allowlist(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    web = tmp_path / "web"
    web.mkdir()
    legacy = web / "existing.css"
    legacy.write_text(".label { font-size: 11px }", encoding="utf-8")
    emitted = gate._emit_allowlist(tmp_path, "Factory#3874")
    assert "rule: small-text" in emitted
    allowlist = tmp_path / "allowlist.yaml"
    allowlist.write_text(
        emitted.replace(gate._REASON_PLACEHOLDER, "Legacy label awaiting migration"),
        encoding="utf-8",
    )
    (web / "new.css").write_text(".label { font-size: 11px }", encoding="utf-8")
    assert gate.check(tmp_path, allowlist) == ["web/new.css:1: small-text — font-size: 11px"]

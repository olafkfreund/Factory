# factory-ui

Single source of truth for the **shared portal chrome** — the cross-portal
command palette and portal switcher that make the four Factory portals read as
one product.

These components were shipped independently into each portal during the portal
UX program and were drifting as four hand-synced copies (the exact "shared by
convention, not code" risk the UX review flagged). This directory makes them
canonical, governed by the same hub-canonical + byte-exact drift-gate convention
the Factory family already uses for `verification-core` and `factory-contracts`.

## Components

| File | What it is | Per-portal input |
|------|------------|------------------|
| `CommandPalette.tsx` | ⌘K palette: fuzzy jump to views/tasks + run actions | The host assembles the flat `commands` list and passes the live `tasks` — the component itself carries no portal-specific data, so it is already identical everywhere. |
| `PortalSwitcher.tsx` | Topbar switcher: the four portals, current one active, others link out | The host passes a single `current` prop (`'plan' \| 'build' \| 'test' \| 'cockpit'`). Sibling URLs come from `VITE_*_URL` with live-portal fallbacks. |

Both are framework-light React + Tailwind that consume the shared shadcn/HSL
token contract (`border`, `bg-card`, `bg-popover`, `bg-muted`, `text-foreground`,
`text-muted-foreground`, `primary`). They render correctly in any portal on that
contract with no extra CSS.

## Who vendors this

The three Tailwind portals — **PFactory** (`current="plan"`), **AIFactory**
(`current="build"`), **TFactory** (`current="test"`) — vendor both files
byte-identical.

**CFactory is intentionally not a consumer** of these files: the cockpit is
hand-rolled CSS on its own token set (design-system Drift B), so it keeps its own
`PortalSwitcher`/`CommandPalette` until it migrates to the `@theme`/HSL contract.
Its `current` is `'cockpit'`.

## Vendoring contract (same as verification-core)

The canonical copies here are the single source of truth. Each consuming portal
hand-vendors them into `apps/frontend-web/src/components/` and MUST keep the
copies **byte-identical** to this canonical. A blocking drift gate in each portal
checks out the hub at a pinned SHA and runs `scripts/check_factory_ui_drift.py`;
a byte mismatch fails the build. Vendored copies are excluded from the portal's
local lint/format (they are governed by the byte-exact gate, not the repo style
config).

To intentionally change a shared component:

1. Land the change here in the hub canonical first (CODEOWNERS-reviewed).
2. Re-vendor it into each portal byte-for-byte.
3. Bump `HUB_PIN_SHA` in each portal's `factory-ui-drift` workflow.

Never edit a vendored copy to satisfy a local style bar.

## Checking drift

```sh
# Check a portal checkout against the hub canonical:
python scripts/check_factory_ui_drift.py --service aifactory --root /path/to/AIFactory

# List which files each portal is expected to vendor:
python scripts/check_factory_ui_drift.py --list

# Built-in self-test (no repo state needed):
python scripts/check_factory_ui_drift.py --self-test
```

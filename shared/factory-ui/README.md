# factory-ui

Single source of truth for the **shared portal design tokens and chrome** — the
OKLCH token set, Tailwind v4 `@theme inline` bridge, cross-portal command
palette, portal switcher and project breadcrumb that make the five Factory
portals read as one product.

These files are canonical, governed by the same hub-canonical + byte-exact
drift-gate convention the Factory family uses for `verification-core` and
`factory-contracts`.

## Files

| File | What it is | Consumers / input |
|------|------------|-------------------|
| `tokens.css` | Plain-CSS OKLCH token ramp (`--f-*` with hex comments): light on `:root`, dark on `.dark`, per-portal `--f-accent` selection via `:root[data-portal=plan\|build\|test\|cockpit\|meet]`, plus shared type sizes, font stacks (`--f-font-sans`, `--f-font-mono`), radius and 4px spacing grid | Vendored by all five portals (`pfactory`, `aifactory`, `tfactory`, `cfactory`, `rfactory`). Plain-CSS portals alias their local variables to `var(--f-*)`. |
| `tailwind-theme.css` | Tailwind v4 `@theme inline` bridge mapping shadcn utility names (`--color-background`, `--color-foreground`, `--color-card`, `--color-popover`, `--color-muted`, `--color-secondary`, `--color-accent`, `--color-border`, `--color-input`, `--color-primary`, `--color-ring`, `--color-destructive`, status and sidebar names), `--font-sans`/`--font-mono`, `--text-*` and `--radius-*` to `--f-*` tokens | Vendored by the three Tailwind portals (`pfactory`, `aifactory`, `tfactory`) alongside `tokens.css` under `apps/frontend-web/src/styles/`. |
| `CommandPalette.tsx` | Cmd-K palette: fuzzy jump to views/tasks + run actions | The host assembles the flat `commands` list and supplies the task lane either as a local `tasks` list (filtered here) or via an async `onSearch(q)` that returns ranked results (federated search, #149). |
| `PortalSwitcher.tsx` | Topbar switcher: the five portals (`plan`, `build`, `test`, `cockpit`, `meet`), current one active, others link out with `var(--f-<portal>)` accent dots | The host passes `current` (`'plan' \| 'build' \| 'test' \| 'cockpit' \| 'meet'`), optional `needsCount` (fleet human-blocked count badge on Cockpit), and optional `project={{ slug, portals }}`. Sibling URLs come from `VITE_*_URL` with live-portal fallbacks. |
| `ProjectBreadcrumb.tsx` | Topbar `Project / <name>` with a searchable switch list; no delete or add (those live on the host's Projects page) | `projects: {slug, name}[]`, `currentSlug`, `onSelect(slug)`, optional `onViewAll()`. Router-neutral: the host navigates. |

`CommandPalette` also takes optional `projects` + `onSwitchProject` (adds a
"Switch project..." action), and `PortalSwitcher` an optional
`project={{ slug, portals }}` that keeps `/p/<slug>` on the named sibling
portals (the rest keep linking to their root until they have `/p/` routes).
Hosts that pass none of these render as before.

## Design tokens and bridge

`tokens.css` defines the Gruvbox-derived warm-neutral role ramp in OKLCH with
verified WCAG 2.2 AA contrast:

- **Every text and accent token** (`--f-text`, `--f-text-secondary`,
  `--f-text-muted`, `--f-plan`, `--f-build`, `--f-test`, `--f-cockpit`,
  `--f-meet`, `--f-success`, `--f-warning`, `--f-danger`, `--f-info`) is at
  least **4.5:1** against `--f-bg` and every surface (`--f-surface-1` through
  `--f-surface-3`) in both light and dark modes.
- **`--f-border-strong`** is at least **3:1** on every surface in both modes.
- **`--f-on-accent`** is at least **4.5:1** on every accent and status fill.

`tailwind-theme.css` uses `@theme inline` so existing shadcn utility classes
(`bg-background`, `bg-card`, `bg-popover`, `bg-muted`, `text-foreground`,
`text-muted-foreground`, `border-border`, `border-input`, `bg-primary`,
`text-primary-foreground`, `ring-ring`, etc.) resolve directly to `--f-*`
without changing component class names.

## Vendoring subsets and destinations

Each portal vendors a declared subset of `shared/factory-ui/`:

| Portal | Vendored files | Destination in portal repo |
|--------|----------------|----------------------------|
| **PFactory** (`plan`), **AIFactory** (`build`), **TFactory** (`test`) | `CommandPalette.tsx`, `PortalSwitcher.tsx`, `ProjectBreadcrumb.tsx` | `apps/frontend-web/src/components/<file>` |
| **PFactory**, **AIFactory**, **TFactory** | `tokens.css`, `tailwind-theme.css` | `apps/frontend-web/src/styles/<file>` |
| **CFactory** (`cockpit`) | `tokens.css` (token-only subset; plain CSS on its own markup) | `apps/frontend-web/src/styles/tokens.css` |
| **RFactory** (`meet`) | `tokens.css` (token-only subset; plain HTML/CSS) | `web/public/tokens.css` |

## Gates

Three hub gates enforce the design system contract:

1. **Drift gate (`scripts/check_factory_ui_drift.py`):**
   - Verifies byte-exact vendoring of each portal's declared subset (`.tsx` into
     `src/components/`, `.css` into `src/styles/` or `web/public/`).
   - Guards against unlisted `*.tsx` and `*.css` files in `shared/factory-ui/`.
   - Tolerates newly added files listed in `NOT_YET_PINNED` while a portal's
     pinned `HUB_PIN_SHA` predates them.
2. **Token contrast self-test (`scripts/check_token_contrast.py`):**
   - Pure stdlib check that parses `tokens.css` and asserts WCAG contrast ratios
     for all text/accent/status tokens against `--f-bg` and `--f-surface-1..3`
     (>= 4.5:1), `--f-border-strong` (>= 3:1), and `--f-on-accent` on all accent
     and status fills (>= 4.5:1) in both light and dark modes.
3. **Small-text ratchet (`scripts/check_banned_constructs.py`):**
   - Rejects sub-12px text in portal frontends (`text-[Npx]` with `N < 12`,
     `text-[0.Nrem]` below `0.75rem`, and CSS `font-size` below `12px` /
     `0.75rem`), ratcheted so new occurrences fail CI immediately.

## Vendoring contract (same as verification-core)

The canonical copies here are the single source of truth. Each consuming portal
hand-vendors its declared files and MUST keep the copies **byte-identical** to
this canonical. A blocking drift gate in each portal checks out the hub at a
pinned SHA and runs `scripts/check_factory_ui_drift.py`; a byte mismatch fails
the build. Vendored copies are excluded from the portal's local lint/format
(they are governed by the byte-exact gate, not the repo style config).

To intentionally change a shared token or component:

1. Land the change here in the hub canonical first (CODEOWNERS-reviewed).
2. Re-vendor it into each consuming portal byte-for-byte.
3. Bump `HUB_PIN_SHA` in each portal's `factory-ui-drift` workflow.

Never edit a vendored copy to satisfy a local style bar.

## Checking drift and contrast

```sh
# Check token contrast ratios (light and dark):
python scripts/check_token_contrast.py

# Check a portal checkout against the hub canonical:
python scripts/check_factory_ui_drift.py --service aifactory --root /path/to/AIFactory

# List which files each portal is expected to vendor:
python scripts/check_factory_ui_drift.py --list

# Built-in self-test (no repo state needed):
python scripts/check_factory_ui_drift.py --self-test
```

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
| `tailwind-theme.css` | Tailwind v4 bridge mapping shadcn color utility names to `--f-*` tokens in `@theme inline`; font stacks and radii in `@theme` keep their CSS variables available to portal styles | Vendored by the three Tailwind portals (`pfactory`, `aifactory`, `tfactory`) alongside `tokens.css` under `apps/frontend-web/src/styles/`. |
| `shell.css` | Plain-CSS layout, controls, states and work cards | Load after `tokens.css`. Use `.dark` and set `data-portal` on the document root. |
| `AppShell.tsx` | Controlled top bar and sidebar, with an optional pipeline strip | Supply navigation and action callbacks, status slots, localized labels and the current view. The portal owns routing, theme application and the Cmd-K shortcut. |
| `ProjectSwitcher.tsx` | Searchable project combobox with recents | Supply projects, the active slug and selection callbacks. |
| `PipelineStrip.tsx` | Stage and failure filters | Supply stage counts, the active stage, and callbacks. Set `alarm` to the stage key on a new failure. |
| `WorkCard.tsx` | Compact, active, failed and expandable work cards | Supply status/actions and expanded content. Progress is a percentage (0–100). Detail navigation and expansion have separate callbacks. |
| `WorkColumn.tsx` | Column count, collapsed-row limit and remembered expansion | Give each item a project ID, item ID, collapse default and render callback. Pass the column's project ID for a project board and omit it for a fleet board. Columns in that scope share the expanded item. |
| `CommandPalette.tsx` | Cmd-K palette: jump to views/tasks and run actions | The host assembles the flat `commands` list and supplies the task lane either as a local `tasks` list (filtered here) or via an async `onSearch(q)` that returns ranked results (federated search, #149). |
| `PortalSwitcher.tsx` | Topbar switcher: the five portals (`plan`, `build`, `test`, `cockpit`, `meet`), current one active, others link out with `var(--f-<portal>)` accent dots | The host passes `current` (`'plan' \| 'build' \| 'test' \| 'cockpit' \| 'meet'`), optional `needsCount` (fleet human-blocked count badge on Cockpit), and optional `project={{ slug, portals }}`. Sibling URLs come from `VITE_*_URL` with live-portal fallbacks. |
| `ProjectBreadcrumb.tsx` | Topbar `Project / <name>` with a searchable switch list; no delete or add (those live on the host's Projects page) | `projects: {slug, name}[]`, `currentSlug`, `onSelect(slug)`, optional `onViewAll()`. Router-neutral: the host navigates. |

`CommandPalette` also takes optional `projects` + `onSwitchProject` (adds a
"Switch project..." action), and `PortalSwitcher` an optional
`project={{ slug, portals }}` that keeps `/p/<slug>` on the named sibling
portals (the rest keep linking to their root until they have `/p/` routes).
The palette and portal switcher use `shell.css` starting with the shared-shell pin.

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

## C2 adoption notes

When a portal adopts the bridge, replace direct legacy color references with
the named utilities. For example, TFactory's `dropdown-menu.tsx:69` uses
`hsl(var(--popover))` and `button.tsx:24` uses `var(--success)`; those call
sites need `bg-popover` and `bg-success` respectively. Check foregrounds too,
such as `text-popover-foreground`, before removing the old variables.

## Vendoring subsets and destinations

Each portal vendors a declared subset of `shared/factory-ui/`:

| Portal | Vendored files | Destination in portal repo |
|--------|----------------|----------------------------|
| PFactory, AIFactory, TFactory, CFactory | `CommandPalette.tsx`, `PortalSwitcher.tsx`, `ProjectBreadcrumb.tsx` | `apps/frontend-web/src/components/<file>` |
| PFactory, AIFactory, TFactory, CFactory | `AppShell.tsx`, `ProjectSwitcher.tsx`, `PipelineStrip.tsx`, `WorkCard.tsx`, `WorkColumn.tsx` | `apps/frontend-web/src/components/factory-ui/<file>` |
| PFactory, AIFactory, TFactory, CFactory | `tokens.css`, `shell.css` | `apps/frontend-web/src/styles/<file>` |
| PFactory, AIFactory, TFactory | `tailwind-theme.css` | `apps/frontend-web/src/styles/tailwind-theme.css` |
| RFactory | `tokens.css`, `shell.css` | `web/public/<file>` |

## Gates

Three hub gates enforce the design system contract:

1. **Drift gate (`scripts/check_factory_ui_drift.py`):**
   - Verifies byte-exact vendoring at the destinations above.
   - Guards against unlisted `*.tsx` and `*.css` files in `shared/factory-ui/`.
   - Tolerates files listed in `NOT_YET_PINNED` for every service while its pin
     predates them. CFactory adds the existing React controls when its pin
     includes `shell.css`.
2. **Token contrast self-test (`scripts/check_token_contrast.py`):**
   - Pure stdlib check that parses `tokens.css` and asserts WCAG contrast ratios
     for all text/accent/status tokens against `--f-bg` and `--f-surface-1..3`
     (>= 4.5:1), `--f-border-strong` (>= 3:1), and `--f-on-accent` on all accent
     and status fills (>= 4.5:1) in both light and dark modes.
3. **Small-text ratchet (`scripts/check_banned_constructs.py`):**
   - Opt in with `--enforce-small-text` after the C2.5 codemod. Default portal
     gate runs leave this rule off while existing small text is migrated.
     When enabled, it rejects sub-12px Tailwind, inline style and CSS text
     sizes in portal frontends and `shared/factory-ui/`.

## Vendoring contract (same as verification-core)

The canonical copies here are the single source of truth. Each consuming portal
hand-vendors its declared files and MUST keep the copies **byte-identical** to
this canonical. A blocking drift gate in each portal checks out the hub at a
pinned SHA and runs the current `scripts/check_factory_ui_drift.py` against
that canonical tree. Add the new paths to the workflow filters and
`src/components/factory-ui/**` to the portal's ESLint ignores when adopting.
CFactory and RFactory add their first drift workflows alongside adoption.

To intentionally change a shared token or component:

1. Land the change here in the hub canonical first (CODEOWNERS-reviewed).
2. Re-vendor it into each consuming portal byte-for-byte.
3. Bump `HUB_PIN_SHA` in each portal's `factory-ui-drift` workflow.

Never edit a vendored copy to satisfy a local style bar.
Coordinate hub rollback with portal pins once shell adoption begins.

## Checking drift and contrast

```sh
# Check token contrast ratios (light and dark):
python scripts/check_token_contrast.py

# Enforce the text-size floor for shared UI:
python scripts/check_banned_constructs.py --root . --allowlist banned-constructs-allowlist.yaml --enforce-small-text

# Check a portal checkout against the hub canonical:
python scripts/check_factory_ui_drift.py --service aifactory --root /path/to/AIFactory

# List which files each portal is expected to vendor:
python scripts/check_factory_ui_drift.py --list

# Built-in self-test (no repo state needed):
python scripts/check_factory_ui_drift.py --self-test
```

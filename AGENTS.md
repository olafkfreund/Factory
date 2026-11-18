# AGENTS.md

Guidance for any coding agent working in the Factory hub repository.

## What this repo is

The program and meta repository of the Factory family: cross-cutting epics, the shared
PARR pipeline contracts, and the canonical standards and scripts that the four services
(PFactory plan, AIFactory build, TFactory verify, CFactory observe) vendor. Product work
lives in the product's own repo; work that spans the family lives here. See `README.md`.

## Layout

| Path | What lives there |
|------|------------------|
| `intent/`, `spec/`, `plan/` | The why, what and how of each task, one `YYYY-MM-DD-<issue>-<slug>.md` per task |
| `standards/` | Shared coding standards, `ruff.toml`, `mypy.ini`, `tsconfig.base.json`; services may only tighten |
| `scripts/` | Hub canonicals (branch protection as code, lint ratchets, gate preflights); several are vendored into services, so fix them here, not in a copy |
| `contracts/`, `shared/`, `apis/` | Cross-service schemas, shared code and API/MCP descriptions |
| `docs/` | The Jekyll site at factory.freundcloud.com, plus compliance, RFCs and benchmark notes |
| `tests/` | Hub tests |
| `.github/workflows/` | CI, gates and drift checks |
| `.claude/skills/` | Agent Skills for hub procedures |

## Workflow

- Branch from `origin/main` as `<type>/<issue>-<description>`; open a PR to `main`. Never
  commit to `main`.
- Any task tracked as an issue, or touching more than one file, goes through
  intent, then spec, then plan, each committed as `status: draft` and approved in its own
  commit (`docs(<stage>): approve <slug> (#<issue>)`) before the next is written and
  before implementation. Typos, a flake lock bump and one-line config changes are exempt.
- Before proposing a design, search the rejected ones:
  `git grep -n -A40 '^## .*Alternatives' spec docs/rfc`.
- Conventional commit titles, at most 100 characters. Stage named paths, never `git add -A`.

## Rules with teeth

- No secrets in the repo, in logs or in PR text. Never read decrypted secret files.
- Do not touch the live cluster from a task; deploys and live changes are the owner's.
- Branch protection is code (`scripts/apply_branch_protection.sh`); do not change it by hand.
- Vendored files in the services are byte-checked against the hub copy: change the hub
  canonical, then re-vendor.
- Honesty over optics: a score, status or doc states what holds today, with evidence.
- No emojis in code, docs or commit messages.

## Checks

CI is the authority; read `.github/workflows/` for what is required. Run the tests under
`tests/` that cover the files you touched, and `git diff --check`.

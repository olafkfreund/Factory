---
status: draft
issue: 3702
intent: intent/2026-11-16-3702-per-org-cockpit-tokens.md
---

# Spec: per-org upstream tokens in CFactory

## Design

Option "one socket per org key", implemented in CFactory only.

- `Settings` gains `pfactory_org_tokens`, `aifactory_org_tokens`,
  `tfactory_org_tokens`: comma-separated `acw_` keys, default empty,
  `repr=False`. Env: `CFACTORY_<SERVICE>_ORG_TOKENS`.
- `Settings.extra_tokens_for(service)` returns the parsed list (stripped,
  blanks dropped, de-duplicated, the primary `token_for` value removed).
- `start_subscribers` starts the existing subscriber once for the primary
  token (unchanged) and once more per extra token, same URL, header
  `Authorization: Bearer <extra>`.
- Ingest is already idempotent (`upsert_from_event` returns `applied`), so an
  event seen on two sockets is broadcast once.
- Logs: the existing subscriber logs the URL and service, never the header.
  The extra subscribers reuse it, so tokens stay out of logs.

Each upstream still enforces `_may_receive` per key, so no key sees more than
before. Nothing is read from the upstream factories' code.

## Alternatives rejected

- Multi-org key: needs a key schema and mint API change in three factories and
  widens a credential. It is the owner's decision and stays open.
- Pass a list in the existing token variable: breaks the single-token contract
  and the `acw_` shape validation.

## Risks

- Unset means identical behaviour. Misconfigured extra key: that socket
  reconnects every 3 s like any failing upstream (debug log only).
- One extra reconnect loop per key. Acceptable at a handful of orgs.

## Verification

Unit tests: parsing and dedupe; defaults give exactly one subscriber per
service; extra tokens give extra subscribers with distinct Bearer headers and
the same URL. `just` test/lint targets for CFactory.

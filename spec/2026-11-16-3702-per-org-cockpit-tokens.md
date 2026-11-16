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
- No cross-socket dedupe in CFactory (Codex: the store does not dedupe
  id-less events). It is not needed: an org-bound key only receives its own
  org's events (#3679 `_may_receive`), so two distinct org keys never see the
  same event. The same key listed twice is removed by the parser.
- Logs: the existing subscriber logs the URL and service, never the header.
  The extra subscribers reuse it, so tokens stay out of logs.

Each upstream still enforces `_may_receive` per key, so no key sees more than
before. Nothing is read from the upstream factories' code.

## Alternatives rejected

- Multi-org key: needs a key schema and mint API change in three factories and
  widens a credential. It is the owner's decision and stays open.
- Pass a list in the existing token variable: breaks the single-token contract.

## Risks

- Unset means identical behaviour. Misconfigured extra key: that socket
  reconnects every 3 s like any failing upstream (debug log only).
- One extra reconnect loop per key. Acceptable at a handful of orgs.

- Duplicates appear only if the owner lists a service-wide (unbound) key as
  an extra token alongside org keys; document that extras must be org-bound.

## Verification

Unit tests: parsing and dedupe; defaults give exactly one subscriber per
service; extra tokens give extra subscribers with distinct Bearer headers and
the same URL. `just` test/lint targets for CFactory.

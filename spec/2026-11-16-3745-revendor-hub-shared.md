---
status: approved
issue: 3745
intent: intent/2026-11-16-3745-revendor-hub-shared.md
---

# Spec: re-vendor hub shared packages

## Design

Copy every `*.py` of `shared/factory-common/factory_common` and `shared/factory-sandbox/agent_sandbox` from hub main `b3844b8b224d1ec198afd7a77221eb67b45fe217` into each repo's vendored directory and write that SHA to the adjacent `.hub-sha`. One PR per repo. Where a hub change breaks a repo test, make the minimal test adaptation in that PR (AIFactory: the sk-ant- sanitize test now exercises a non-Anthropic sk- key because the fleet table owns sk-ant-).

## Alternatives rejected

A single hub-side PR: the vendored copies live in the product repos. Pinning each repo to a different SHA: no benefit, more review.

## Risks

Fleet redaction now also redacts sk-ant- strings in logs and errors, which could change tests asserting old placeholders; CI on each PR is the check.

## Verification

`check_factory_sandbox_drift.py` per repo, `diff -r` of factory_common against the canonical, the repos' secret/url-safety/logsafe tests, repo CI, then Factory `scripts/check_pin_freshness.py`.

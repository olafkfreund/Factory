<!--
Factory task intake (RFC-0011) for GitLab.

GitLab issue templates cannot render a dropdown, so set the difficulty with a
scoped label below and keep ONE of the difficulty lines. The Factory poller
reads the `factory:<tier>` label; the body fields feed the contract.

Difficulty drives model / planning / human gate / verification floor / merge:
  factory:low    — cheap/local model, no planning, no human, auto-merge when green
  factory:medium — sonnet, light planning, async approval
  factory:hard   — opus, full PFactory plan, blocking approval, deepest verification
A migration (rewrite/port) forces factory:hard + an equivalence check.

See https://factory.freundcloud.com/rfc/label-driven-intake/
-->

/label ~"pfactory"

<!-- Keep exactly ONE of the next three lines: -->
/label ~"factory:low"
<!-- /label ~"factory:medium" -->
<!-- /label ~"factory:hard" -->

<!-- For a rewrite/migration, also add (and it will be promoted to factory:hard): -->
<!-- /label ~"plan-type:migration" -->

## Context

<!-- What needs to happen and why. Link relevant code, docs, or prior issues. -->

## Acceptance criteria

<!-- Testable conditions; these become the verification targets. -->
- 
- 

## Target repository

<!-- owner/repo or GitLab project path the change lands in. -->

## Change mode

<!-- create | modify | migration  (migration = rewrite/port, forces factory:hard) -->
create

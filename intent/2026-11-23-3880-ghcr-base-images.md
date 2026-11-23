---
status: approved
issue: 3880
author: olafkfreund
---

# Intent: releases do not depend on Chainguard availability

See issue #3880. The owner said "we need to fix that as well. Open an issue and solve it" (2026-11-23), after cgr.dev and apk.cgr.dev outages blocked three releases.

## Constraints
- Keep the same Chainguard bases and packages, pinned by digest. This is no security downgrade.
- No change to runtime behaviour.
- Each portal owns its own base build.

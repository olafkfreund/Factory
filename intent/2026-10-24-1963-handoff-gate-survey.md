---
status: draft
issue: 1963
author: olafkfreund
---
# Intent: survey the gate at each inter-agent handoff

**Problem:** #1963 asks for a deterministic floor under the model-assisted verify gate. Nobody has written down which deterministic check, if any, guards each handoff between factories.
**Outcome:** `docs/dev/handoff-gate-survey.md` covers PFactory to AIFactory, AIFactory to TFactory and TFactory back to AIFactory, naming each gate with file:line. A handoff with no gate gets its own filed issue, linked from the survey. Linked from #1963; closes it once the other slices are done.
**Affected:** Factory `docs/dev/`; reads AIFactory, PFactory, TFactory source.
**Constraints:** Doc only, no code. Cite code on each repo's default branch.
**Open questions:** None.

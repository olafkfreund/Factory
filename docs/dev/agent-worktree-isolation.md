# When an agent's worktree disappears underneath it

Factory#616. On 2026-08-07 several agents running with `isolation: "worktree"`
lost their working directory while still running. The Bash tool then refuses
every command:

```
This agent is isolated in the worktree
/mnt/data/Source-home/GitHub/Factory/.claude/worktrees/agent-<id>, but its
working directory ".../agent-<id>" no longer exists ...
```

The refusal is correct -- falling back to the parent session's shared checkout
would let an isolated agent write into a tree other agents are using. The problem
is the disappearance, not the guard.

This document records what was measured, what the honest conclusion is, the one
rule that is actually ours to keep, and what would be needed to fix the rest.

## What the damage actually is

Narrower than it first looks, and the shape matters more than the size.

The **files survive**. Removing a worktree does not delete the branch it was on,
so anything committed is still reachable. Both stranded agents on 2026-08-07 had
already committed and pushed; that was timing, not design.

What is lost is **execution**. Work is truncated at an arbitrary point while the
agent's EARLIER reports still read as complete. One agent lost a measurement it
could no longer re-run, and the result had to be published as unmeasured. Two
finished their last actions through the GitHub API, which needs no shell. An
agent that lost its shell just before pushing would report progress and leave
nothing behind.

That is the danger: not data loss, but a truncated run that looks finished.

## Measured, 2026-08-07

**The harness marks a live agent's worktree with a git lock.**

```
$ git worktree list --porcelain
worktree /mnt/data/Source-home/GitHub/Factory/.claude/worktrees/agent-a0fe0977b570fc340
branch refs/heads/worktree-agent-a0fe0977b570fc340
locked claude agent agent-a0fe0977b570fc340 (pid 311603 start 12662981)
```

36 agent isolation worktrees were registered on the hub checkout; 8 carried that
lock. The lock reason names the parent session's pid and start time, so it is a
machine-readable liveness marker, not a decoration.

**What that lock does and does not stop.** Proven in a scratch repository rather
than asserted:

| Command against a locked worktree | Result |
|---|---|
| `git worktree remove <path>` | refused, exit 128, `fatal: cannot remove a locked working tree` |
| `git worktree prune` | ignores it entirely; directory still present |
| `git worktree remove -f -f <path>` | removed |
| `rm -rf <path>` | removed (git is not consulted at all) |

And in every case the branch survives the removal, which is why the files
survived on 2026-08-07.

**Nothing in this repository manages those worktrees.** A grep for
`worktree add`, `worktree remove`, `worktree prune` and `worktrees/` across every
`.sh`, `.py`, `.yml`, `.json` and `.md` in the hub returns no hit that touches
`.claude/worktrees/`. The nearest thing is
`docs/dev/benchmark-matrix-runbook.md`, which runs `git worktree prune` against
an AIFactory workspace -- a different tree, and prune is the safe verb anyway.

**Cleanup is documented harness behaviour.** The Agent tool's own contract says
`isolation: "worktree"` gives the agent a git worktree "auto-cleaned if
unchanged". Removal is a feature. The defect is that "unchanged" is evaluated
against a tree that may belong to an agent still working in it -- an agent that
has just committed and pushed looks exactly like an agent that did nothing.

## The honest conclusion

**We cannot fix this from this repository.** The removal is performed by the
harness, on a trigger we cannot see, gate, or hook. No configuration in this repo
influences it.

There is exactly one removal path that IS ours: a human or an agent tidying up
the accumulated worktrees. With 36 of them on the checkout, somebody eventually
will, and the naive form of that cleanup is what would strand every live agent at
once.

## The one rule that is ours

**Clean up agent worktrees with plain `git worktree remove`. Never `-f -f`, never
`rm -rf .claude/worktrees/`.**

```bash
# Safe: git refuses the locked (live-agent) and dirty ones for you.
git worktree remove .claude/worktrees/agent-<id>
```

Note what makes this a control rather than an instruction: **the safe command is
also the default command.** Git refuses a locked worktree on its own, with a
message naming the lock reason. Getting it wrong requires deliberately typing
`-f -f` or reaching past git with `rm -rf`. Nothing detects a violation after the
fact -- but nothing needs to, because the unsafe form is the one you have to go
out of your way to write.

Two supporting habits, which are advisory and have no detector, stated as such:

- **Push early and often.** Do not batch a single push at the end. This is the
  only reason the 2026-08-07 losses were recoverable, and it is the only
  mitigation that works regardless of what removed the tree.
- **Do not run `gh pr merge --delete-branch` while agents hold worktrees.** It
  errors on any branch a worktree has checked out (`cannot delete branch 'X' used
  by worktree at ...`) and leaves the remote branch already deleted. It is not
  the cause of Factory#616 -- it deletes branches, not directories -- but it is a
  real, separate way to half-break a live agent's state.

## What would be needed to fix the rest

Harness-side, in the Claude Code agent runtime:

1. **Do not remove a worktree whose lock names a live pid.** The marker already
   exists and already carries the pid; the auto-clean path evidently does not
   consult it, or consults it and forces past it.
2. **Do not treat "clean tree" as "finished".** An agent that has committed and
   pushed is the normal mid-run state, not an idle one.
3. **Tell the agent.** Today the first signal is a refused Bash call. An
   explicit notification would let an agent mark its own report as truncated
   instead of leaving earlier output reading as complete -- which is the part
   that caused a wrong conclusion to be published on 2026-08-07 and corrected
   afterwards.

None of the three can be done from a pull request in this repository. Until they
are, an agent's isolation worktree can vanish mid-run, and the only defences are
the rule above and pushing early.

## Related

- `docs/compliance/agent-identity.md` -- the same session's other
  agent-infrastructure defect (Factory#611): a constraint with no mechanism
  behind it.
- `docs/dev/gate-honesty.md` -- the general shape, a check that reports a result
  while measuring nothing.

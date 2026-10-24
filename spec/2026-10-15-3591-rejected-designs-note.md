---
status: approved
issue: 3591
intent: intent/2026-10-15-3591-rejected-designs-note.md
---

# Spec: make rejected designs easy to find before proposing one again

## Design

A convention note, not a directory. In `README.md` "Repository layout"
(`:70-81`), add one bullet for `intent/`, `spec/` and `plan/` (the
README does not mention them today) that says:

- each task's why/what/how lives there, one slug per task;
- a rejected design is recorded in the `## Alternatives rejected` section
  of the spec (or RFC) that rejected it, with the reason;
- before proposing a design, search those sections, with the command
  `git grep -n -A40 '^## .*Alternatives' spec docs/rfc`;
- re-proposing a rejected design needs new evidence, cited in the new spec.

The spec's `## Alternatives rejected` heading is already the stable,
greppable record (14 of 14 hub specs use it verbatim), dated by the slug and
linked to its issue by the frontmatter. That already gives each entry the
"what, why, date, link" the issue asks for.

## Alternatives rejected

- **A `docs/rejected/` directory, one record per design.** Duplicates the
  spec sections, adds a second write per rejection that nothing enforces,
  and drifts. Revisit if the grep stops being enough, e.g. rejections made
  outside any spec.
- **A generated index of all "Alternatives rejected" sections.** A script, a
  check and a committed output for something one `git grep` already does.
- **Putting the note in the artifact-workflow skill.** The skill lives
  outside this repo; the README is what a contributor here reads.

## Risks

- A rejection made only in an issue comment or PR review is not found by
  the grep. Accepted: the note asks for the reason to land in a spec.

## Verification

- The README renders the bullet in the layout list.
- The command in the note runs from the repo root and lists the sections
  (`git grep -c '^## .*Alternatives' spec docs/rfc` is non-zero).
- No other file changes.

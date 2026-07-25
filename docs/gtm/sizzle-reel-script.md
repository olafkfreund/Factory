# 60-Second Sizzle Reel: Script, Shot List, and Storyboard

Source issue: Factory#250 (parent epic #240, positioning lock #248).
Status: production-ready script for a human editor. The video render is a follow-up; this file is the cut sheet.

Hard rules:
- No audio or on-screen claim beyond current capability. VAL-2 is the ceiling; never imply VAL-3 or "fully autonomous, no humans".
- No emojis or icons anywhere in captions.
- Every VO line must be defensible from a recorded demo.

Positioning thesis (drives every beat):
"The self-hosted governance and verification layer for autonomous coding: the factory that runs your agents' code, tests it for real, and refuses to overclaim." Lead with trust-verified, not code-faster.

Narrative arc (five acts across 60s):
1. Hook: the trust gap (0:00-0:08)
2. The factory runs real agents on a real repo (0:08-0:22)
3. Verification catches a dishonest coder (0:22-0:38)
4. Governance, self-host, and audit (0:38-0:52)
5. Close and CTA (0:52-1:00)

---

## Second-by-second shot list

Format per beat: timecode | on-screen visual (exact asset or FRESH capture) | on-screen caption | voiceover.

### Act 1 - Hook: the trust gap (0:00-0:08)

- 0:00-0:03
  - Visual: black card, then a fast type-on of the stat. No footage.
  - Caption: "84% of developers use AI to code. 29% trust the output."
  - VO: "Everyone's shipping AI-written code. Almost no one trusts it."

- 0:03-0:08
  - Visual: FRESH capture - the animated cockpit execution DAG mid-run (CFactory task-detail live graph). Fallback still: docs/assets/screenshots/tour/flow/05-cfactory-dag.png with a slow push-in.
  - Caption: "So we built the factory that checks."
  - VO: "So we built the layer that runs your agents' code and proves whether it actually works."

### Act 2 - The factory runs real agents on a real repo (0:08-0:22)

- 0:08-0:12
  - Visual: docs/assets/screenshots/tour/flow/01-pfactory-plan.png (PFactory plan), quick pan across the plan.
  - Caption: "1. Plan. A real repo, a signed task contract."
  - VO: "It starts with a plan on a real repository - reviewed, signed, and governed."

- 0:12-0:17
  - Visual: docs/assets/screenshots/tour/flow/02-aifactory-subtasks.png into docs/assets/screenshots/tour/flow/03-aifactory-logs.png (AIFactory subtasks then live logs).
  - Caption: "2. Build. Autonomous agents write the code."
  - VO: "Autonomous coders pick up the work and build."

- 0:17-0:22
  - Visual: docs/assets/demos/parr-deploy-then-verify.gif (PARR run, first half - deploy). Let the GIF motion carry the beat.
  - Caption: "3. Run. Not a benchmark. Your code, executed."
  - VO: "Then the factory does what a score never can - it runs the code for real."

### Act 3 - Verification catches a dishonest coder (0:22-0:38)

- 0:22-0:27
  - Visual: docs/assets/screenshots/tfactory/python-unit.gif (tests executing green), held briefly to build false confidence.
  - Caption: "The coder said: all tests pass."
  - VO: "The agent reported success. Its own tests were green."

- 0:27-0:33
  - Visual: FRESH capture - TFactory report showing the acceptance-criteria (AC) ledger with an unmet criterion flagged, and the VAL level downgrading. Fallback still: docs/assets/screenshots/tour/flow/04-tfactory-report.png with a highlight overlay on the failed criterion.
  - Caption: "The factory checked the claim against the contract."
  - VO: "But the factory re-ran everything against the signed contract - and the claim didn't hold."

- 0:33-0:38
  - Visual: continue the FRESH TFactory report capture; animate the assurance badge stepping down (for example VAL-2 to a capped/failed state) with the AC ledger row turning red.
  - Caption: "Verified assurance downgraded. Overclaim refused."
  - VO: "It caught the dishonest coder, downgraded the assurance level, and refused to overclaim."

### Act 4 - Governance, self-host, and audit (0:38-0:52)

- 0:38-0:43
  - Visual: docs/assets/screenshots/evidence/mfa-otp-challenge.png into docs/assets/screenshots/evidence/mfa-authenticated-account.png (MFA browser test logging in and capturing evidence).
  - Caption: "Browser tests log in for real and capture evidence."
  - VO: "Its browser tests log into real apps, through MFA, and screenshot the proof."

- 0:43-0:48
  - Visual: docs/assets/screenshots/pfactory/14-approval.png (HITL approval) or docs/assets/screenshots/cfactory/mission-control.png; brief cut to docs/assets/screenshots/cfactory/audit.png (audit trail).
  - Caption: "Humans approve. Every agent call disclosed."
  - VO: "A human approves the merge, with every agent action disclosed and logged."

- 0:48-0:52
  - Visual: FRESH capture - a local-model run with the data-egress badge showing no external egress. Fallback still: docs/assets/screenshots/cfactory/tokens.png (token/usage panel) with an egress caption overlay.
  - Caption: "Self-hosted. Your models. Your data never leaves."
  - VO: "Run it self-hosted on your own models - your code never leaves your walls."

### Act 5 - Close and CTA (0:52-1:00)

- 0:52-0:57
  - Visual: quick 3-frame montage - docs/assets/screenshots/tour/flow/05-cfactory-dag.png, docs/assets/screenshots/tfactory/polyglot.gif (one loop), docs/assets/screenshots/cfactory/audit.png. Rhythmic cuts on the beat.
  - Caption: "Plan. Build. Run. Verify. Govern."
  - VO: "Plan, build, run, verify, govern - one factory, end to end."

- 0:57-1:00
  - Visual: logo lockup on a clean card; one-liner types on.
  - Caption: "The factory that runs your agents' code, tests it for real, and refuses to overclaim."
  - VO: "The factory that refuses to overclaim." (End card holds the URL.)

---

## Shot-source table

| Beat | Asset | Type |
|------|-------|------|
| 0:00-0:03 | Stat card (84% / 29%) | FRESH - motion-graphics card, no capture |
| 0:03-0:08 | Animated cockpit DAG mid-run (CFactory task-detail) | FRESH capture (still fallback: tour/flow/05-cfactory-dag.png) |
| 0:08-0:12 | tour/flow/01-pfactory-plan.png | EXISTING |
| 0:12-0:17 | tour/flow/02-aifactory-subtasks.png + tour/flow/03-aifactory-logs.png | EXISTING |
| 0:17-0:22 | demos/parr-deploy-then-verify.gif | EXISTING |
| 0:22-0:27 | tfactory/python-unit.gif | EXISTING |
| 0:27-0:33 | TFactory report: AC ledger + VAL downgrade | FRESH capture (still fallback: tour/flow/04-tfactory-report.png) |
| 0:33-0:38 | TFactory report: assurance badge step-down animation | FRESH capture (same source as above) |
| 0:38-0:43 | evidence/mfa-otp-challenge.png + evidence/mfa-authenticated-account.png | EXISTING |
| 0:43-0:48 | pfactory/14-approval.png + cfactory/audit.png (+ cfactory/mission-control.png) | EXISTING |
| 0:48-0:52 | Local-model run with data-egress badge | FRESH capture (still fallback: cfactory/tokens.png + overlay) |
| 0:52-0:57 | tour/flow/05-cfactory-dag.png + tfactory/polyglot.gif + cfactory/audit.png | EXISTING |
| 0:57-1:00 | Logo + one-liner end card | FRESH - motion-graphics card |

Summary of the gap for the editor:
- EXISTING (cut directly): the plan/build/run sequence, the passing-tests GIF, MFA evidence, HITL approval, audit trail, closing montage.
- FRESH captures needed (4 screen recordings + 2 motion cards):
  1. Animated cockpit DAG mid-run (hero shot). This is the one beat the epic explicitly calls animated; the static still is only a fallback.
  2. TFactory report showing the AC ledger with a failing criterion and the VAL level downgrading (the payoff of the whole reel - worth a clean, real capture from a demo run, not a mock).
  3. Assurance badge step-down (can be captured in the same TFactory session as #2).
  4. Local-model run with the data-egress badge visible.
  - Plus two motion-graphics cards (opening stat, closing one-liner) built in the editor, no capture.

Note: the VAL-downgrade capture and the egress-badge capture require the live cluster and a real demo run (see #242 flagship demo and #247 self-host demo). Do not stub or mock these frames - a fabricated "caught" moment would itself be an overclaim.

---

## Music and tone notes

- Arc: restrained and slightly tense in Acts 1-3 (the trust problem, the false-green moment), resolving to steady confidence in Acts 4-5. Never triumphant or hype-y; the product's whole promise is that it does not oversell.
- Track: minimal electronic or muted piano with a low pulse; a single tension lift at 0:22 (the "all tests pass" fake-out) and a clean downbeat at 0:33 (the catch). Resolve warm at 0:48-1:00.
- Sound design: a soft negative cue (not a harsh alarm) on the VAL downgrade at 0:33 - understated, matching a system that reports facts rather than dramatizes.
- Voiceover: calm, technical, credible - an engineer talking to engineers, not an ad read. Slightly slower on the closing line.
- Pacing: 0:00-0:22 measured; 0:22-0:38 is the emotional core, hold shots long enough to read the ledger; 0:52-1:00 tighten cuts, then land.
- Captions: high-contrast, sans-serif, safe for muted autoplay (most feed views have no sound - the reel must fully read on captions alone).

Closing one-liner (end card and final VO):
"The factory that runs your agents' code, tests it for real, and refuses to overclaim."
Sub-line under it on the end card: "Self-hosted governance and verification for autonomous coding."

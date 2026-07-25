# Demo runbook: Self-host + local-model data-egress control

Tracking: Factory#246. Recording is a follow-up; this document is the runbook.

## The point (one line)

Your code and prompts never leave your infrastructure - provably, because the
fleet runs fully self-hosted and can drive every PARR phase on a local model
behind a fail-closed egress policy.

## Who this is for

Regulated and security-conscious buyers: banks, health, defense, public sector -
anyone whose rule is "our source code does not get sent to a third-party
inference API." This is the buyer from the run-locally story and from the
regulated-enterprise scenario in `docs/why.md`: "BYO / air-gapped LLMs with
egress auditing."

## What is real (ground truth before you demo)

Do not claim anything the fleet does not do. These are the real, shippable
capabilities this demo shows:

- Model-agnostic multi-provider factory. AIFactory routes by model string across
  Claude, OpenAI, Gemini, Ollama, vLLM, Codex and Copilot
  (`providers/factory.py`, `phase_config.infer_provider_from_model`). See
  `docs/why.md`, "How we use LLMs and AI."
- Per-stage (per-phase) model selection. RFC-0014 defines a `phase_models` map,
  e.g. `{ "planning": "opus", "coding": "sonnet", "qa": "haiku",
  "test_gen": "ollama:qwen" }`. Set every phase to a local model and no phase
  calls out. See `docs/rfc/0014-cost-aware-model-and-runtime-routing.md`.
- Ollama is a first-class, local-class provider. The model catalog in RFC-0014
  lists `"ollama:<model>": { "provider": "ollama", "class": "local",
  "price": {"mode": "local"} }`. Local models are costed as time, not dollars -
  no metered API bill (billing-mode: `metered | subscription | local`).
- Fully self-hosted fleet. All four services run on your own cluster; the fleet
  today runs against an on-prem Ollama (gemma / qwen) on the local box. See
  `docs/run-locally.md`.
- Fail-closed egress control. Build pods run under a strict egress NetworkPolicy:
  default-deny, DNS plus the binary/model caches only; RFC1918 private ranges are
  handled explicitly and nothing arbitrary leaves the cluster. This is the same
  policy documented in the BYO-Ollama post
  (`docs/_posts/2026-06-14-bring-your-own-ollama-cloudflare-tunnel.md`) and the
  sandbox runtime class (`docs/security/sandbox-runtime-class.md`). The control
  is default-deny, so it fails closed: if a route is not allowed, the call does
  not happen.
- Outbound PII scrub (contrast option). When a buyer DOES use a cloud model, the
  LiteLLM gateway enforces per-org budgets, allow-lists and PII-redacted audit
  logs - the outbound scrub - so even the cloud path is governed. See
  `docs/why.md`, "Enterprise controls."

The honest framing: for a local run the pod-to-model call stays on your private
network (in-cluster Ollama service or an on-prem host). The proof is not a slide;
it is a network view showing zero packets to any third-party inference endpoint.

## Setup

Precondition: a running self-hosted fleet (four services up per
`docs/run-locally.md`) with Ollama reachable in-cluster / on-prem, and at least
one model pulled (e.g. `ollama pull qwen3` or the gemma model already on the
box).

1. Point every PARR phase at a local model. Set the `phase_models` map so all
   four roles resolve to the `ollama` provider:
   `planning`, `coding`, `qa`, `test_gen` -> `ollama:<model>`. Confirm the
   provider factory infers `provider = ollama, class = local` for each.
2. Pick a task to run. Use a small but real greenfield spec (the standard demo
   service is fine) so the run exercises plan -> build -> verify end to end
   without needing external toolchains that themselves egress.
3. Open two panes for capture:
   - the CFactory cockpit (`http://localhost:3110`) for the live PARR board;
   - a network/egress view on the build pod - live connection list
     (`ss -tnp` / conntrack) or the NetworkPolicy plus a tcpdump filtered to
     the well-known inference hosts (api.anthropic.com, api.openai.com,
     generativelanguage.googleapis.com).
4. Pre-flight the negative proof: with the fleet idle, confirm the filtered
   capture shows nothing. This is the baseline you contrast against during the
   run.

## Shot list

1. Model config = local. Show the `phase_models` / model-catalog config with
   every phase resolving to `ollama:<model>`, `provider: ollama`, `class: local`.
   Show the cockpit / billing pill reading tokens-and-time, not dollars
   (billing-mode `local`) - visual proof there is no metered cloud call.
2. Run a PARR task end to end on local models. Kick off the task; let PFactory
   plan, AIFactory build, TFactory verify, all on the local model. Show the
   cockpit board advancing through the phases to a real verdict. The point of
   the shot: a full plan-build-verify loop completed and never left the box.
3. The proof of no third-party egress. This is the hero shot. During the run,
   show the live network view on the build pod: zero connections to any external
   inference host. Then show WHY - the fail-closed egress control:
   - the default-deny egress NetworkPolicy on the build pod;
   - a deliberate failure: attempt an outbound call to
     `https://api.anthropic.com` from inside the pod and watch it be refused /
     time out. Fail-closed, demonstrated, not asserted.
4. Contrast: the default cloud path. Flip one phase back to a cloud model
   (`coding -> sonnet`), re-run, and show the same network view now lighting up a
   443 connection to the provider. This makes the local run's silence meaningful.
5. Contrast: the governed cloud path. With the cloud model selected, show the
   LiteLLM gateway's PII-redacted audit log - the outbound scrub - so the message
   is not "cloud is unsafe" but "even the cloud path is governed; local is
   air-tight."

## Narration

"Every AI company's pitch has the same asterisk: your code goes to someone
else's model. For a bank or a hospital, that asterisk is a deal-breaker.

Here is the Factory running fully self-hosted. Watch the model configuration -
plan, build, QA and test-generation are all pointed at a local Ollama model on
our own hardware. The cost pill reads time, not dollars, because nothing is
metered - nothing is called.

Now I run a real task: plan, build, verify, end to end. And here is the part
that matters - the network view on the build pod. Nothing. Zero packets to any
inference API. Not because we asked nicely; because the egress policy is
default-deny and fails closed. Watch: I try to reach an external model API from
inside the pod - refused.

For contrast, I switch the coding phase to a cloud model. Same view - now there
is one 443 connection to the provider. And even that path is governed: here is
the gateway's audit log with PII redacted on the way out.

So you get a real choice, and both sides are provable. Local: your code never
leaves your infrastructure. Cloud: every call is budgeted, allow-listed and
scrubbed. For a regulated buyer, that is the difference between a pilot and a
policy exception."

## Existing assets vs fresh capture

- Fresh capture (primary): the terminal / network view proving no external calls,
  and the deliberate fail-closed egress refusal. This does not exist yet and is
  the whole point of the demo - capture it live.
- Fresh capture: the `phase_models` config showing all-local, and the cockpit
  billing pill in `local` mode.
- Reusable: the cockpit PARR board footage and the plan-build-verify walkthrough
  overlap with the standard factory demo; reuse framing but re-capture with the
  local-model config so the run is internally consistent.
- Reference, do not re-record: the BYO-Ollama post and RFC-0014 are the written
  backup for anyone who wants the mechanism in detail.

## Proof takeaway

Data residency and sovereignty, demonstrated rather than promised: on a
self-hosted deployment with local models, source code and prompts never cross the
perimeter, and the control that guarantees it is fail-closed by default. When a
buyer chooses the cloud path instead, it is budgeted, allow-listed and
PII-scrubbed. This is the differentiator for regulated and security buyers, and
it ties directly into the compliance program (Factory#310): the egress control
and the redacted audit trail are evidence you can hand an auditor, not a claim on
a slide.

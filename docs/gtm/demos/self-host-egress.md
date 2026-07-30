# Demo runbook: Self-host + local-model data-egress control

Tracking: Factory#246.

## Recorded artifacts

Captured live on the k3d cluster `factory` on 2026-07-30 against
`ghcr.io/olafkfreund/pfactory:sha-5d6797e` (== PFactory `main` at `5d6797e`).

| Artifact | What it is |
| --- | --- |
| `docs/assets/demos/self-host-egress.gif` | The screencast: baseline egress, fail-closed policy, a real local-model coding call, local verify, provider swap. |
| `docs/assets/demos/self-host-egress-badge.png` | The CLI badge shot: `byo_llm.py` for two local endpoints and one managed one. |
| `docs/assets/demos/self-host-egress.cast` | The raw asciicast the GIF was rendered from. Plain text - replay it or grep it to check any frame. |

The GIF is rendered at 1.6x speed with idle gaps capped at 1.2s. Nothing is cut:
the `.cast` is the unmodified capture.

![Self-host egress demo: fail-closed policy, a local-model coding run, and the provider swap](/assets/demos/self-host-egress.gif)

![byo_llm.py egress classification for two local endpoints and one managed one](/assets/demos/self-host-egress-badge.png)

## What the recording actually proves

Read this before showing the recording to anyone. The demo's claim is a security
claim, so the standard is higher than "a green badge appeared".

Proven by measurement, in the recording:

- The coding-stage model call went to `172.18.0.1:11434` - the k3d host gateway,
  an RFC-1918 private address on the operator's own box. `ss -tn state
  established` inside the pod's network namespace, taken while the call was in
  flight, shows that one socket and no others.
- While that call ran, `api.anthropic.com`, `api.openai.com` and
  `generativelanguage.googleapis.com` were all unreachable from that pod
  (`curl` exit 7, connect time 0). The same three answered 405 / 401 / 403 from
  the same pod moments earlier with no policy in place. So a leak to a managed
  model API during the run could not have succeeded quietly - it would have
  failed the run.
- The same code, pointed at `api.openai.com`, fails closed with the policy on
  (`Errno 111 Connection refused`) and connects with it off (`HTTP 401` - the
  remote server answered, so the prompt reached a third party). The control, not
  the wording, is what makes the difference.
- Verify ran locally too, and caught a real defect in the local model's output.

NOT proven, and the recording says so on screen:

- The `local` verdict from `byo_llm.py` is a **classification of the configured
  endpoint**, not a measurement of the wire. It cannot prove non-egress and must
  never be presented as if it does. It is corroborated here by the network
  measurement above; on its own it is the software asserting its own honesty.
- **The `factory` namespace has no egress NetworkPolicy today.** The
  default-deny policy in the recording was applied to an isolated demo namespace
  for the take. The fleet's real build pods are not fail-closed yet - see the
  correction below.
- The recording covers the coding and verify stages of one task. It is not a
  full four-service PARR run driven through PFactory, AIFactory and TFactory on
  local models.

The badge screenshot contains emoji glyphs because `byo_llm.py` puts them in the
badge strings. That is real product output, shown unedited rather than censored;
PFactory#400 tracks replacing them with plain text, after which re-shoot the PNG.

## Reproducing the measurement

The whole control is this one object. `podSelector` scopes it to the pod under
test; the only permitted egress is DNS and the local model endpoint.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: local-model-only
  namespace: egress-demo
spec:
  podSelector:
    matchLabels:
      app: probe
  policyTypes:
    - Egress
  egress:
    # DNS only, to the in-cluster resolver.
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # The self-hosted Ollama endpoint on the host gateway. Nothing else.
    - to:
        - ipBlock:
            cidr: 172.18.0.1/32
      ports:
        - protocol: TCP
          port: 11434
```

`172.18.0.1` is the k3d host gateway on this cluster - check yours with
`kubectl --context factory -n <ns> exec <pod> -- getent hosts host.k3d.internal`
before reusing the manifest.

Then, from inside the selected pod, the three checks that make up the proof:

1. `curl` each managed inference host before and after applying the policy.
   Reachable (405 / 401 / 403) becomes refused (exit 7).
2. Run the coding call against the local endpoint and, while it is in flight,
   `ss -tn state established` in the same pod. Exactly one socket, peer
   `172.18.0.1:11434`.
3. Point the same code at `api.openai.com` with the policy on, then off. Refused,
   then HTTP 401 - proving the policy is what changes the outcome.

## The point (one line)

Your code and prompts never leave your infrastructure - provably, because the
fleet is fully self-hosted, drives its coding and verify stages against a local
model, and can be run behind a fail-closed egress policy that makes a leak fail
the build instead of passing silently.

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
- Fail-closed egress control is **enforceable but not deployed**. Corrected
  2026-07-30: an earlier revision of this runbook stated that build pods already
  run under a strict default-deny egress NetworkPolicy. They do not.
  `kubectl --context factory get netpol -A` returns policies in `argocd` only -
  the `factory` namespace has none, so the fleet's own build pods are not
  fail-closed today. What was verified is that the mechanism works on this
  cluster: k3s enforces NetworkPolicy, and the default-deny policy shown in the
  recording did block all three managed inference APIs while leaving the local
  Ollama endpoint reachable. Treat this as "we demonstrated the control on demand"
  and not "it is on in production". Tracked as Factory#462.
- Outbound PII scrub (contrast option): **not deployable as a shot today.** The
  LiteLLM gateway described in `docs/why.md` "Enterprise controls" is not running
  on this cluster (no litellm workload in any namespace, checked 2026-07-30), so
  shot 5 below cannot be captured. Do not promise a live audit-log view until it
  is deployed. Tracked as Factory#463.
- Do not use the planning stage as evidence. PFactory's planner is reported to be
  deterministic - no LLM call - which would make "the planning stage stayed local"
  trivially true and therefore worthless as proof that the egress classifier or a
  local model works. That report is also not fully consistent with the deployed
  configuration: the pfactory pod carries `CLAUDE_CODE_OAUTH_TOKEN`,
  `OPENAI_API_KEY`, `GEMINI_API_KEY` and
  `PFACTORY_EXECUTION_MODEL=claude-sonnet-4-5-20250929` (checked 2026-07-30).
  Whichever is true, the meaningful demonstration is the coding and verify
  stages - which is what the recording covers - so do not lean on planning either
  way without confirming it first.

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

This is the full target list. The 2026-07-30 recording covers shots 3 and 4 - the
hero shots - plus a local coding-and-verify sequence, and deliberately does not
attempt 1, 2 or 5:

| Shot | In the recording? | Note |
| --- | --- | --- |
| 1. Model config = local, billing pill in `local` mode | Partly | Shows the configured local endpoint and AIFactory enumerating the local models over it. No cockpit billing pill - not captured. |
| 2. Full four-service PARR run on local models | No | The recording runs the coding and verify stages against the local model directly. Driving PFactory -> AIFactory -> TFactory on local models is blocked on AIFactory#1099 (local endpoint resolution) and is slow on a 14B model. |
| 3. Proof of no third-party egress, fail-closed | Yes | The hero shot. Measured, not asserted - see "What the recording actually proves". |
| 4. Contrast: the cloud path lights up | Yes | Same code pointed at `api.openai.com`: refused with the policy on, HTTP 401 with it off. |
| 5. Contrast: governed cloud path, LiteLLM audit log | No | Not capturable - the gateway is not deployed (Factory#463). |

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

Written for the full target shot list. Two paragraphs of it - the all-phases model
config, and the LiteLLM audit log - describe shots the 2026-07-30 recording does
not contain (shots 2 and 5 above). Do not read those aloud over that recording.

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

- Captured 2026-07-30 (primary): the terminal / network view proving no external
  calls, and the deliberate fail-closed egress refusal. See "Recorded artifacts"
  at the top. Re-record it if the cluster's host-gateway address changes or once
  Factory#462 puts a real policy on the fleet's own build pods, at which point the
  take can be made against `factory` instead of an isolated namespace.
- Still to capture: the `phase_models` config showing all-local, and the cockpit
  billing pill in `local` mode.
- Reusable: the cockpit PARR board footage and the plan-build-verify walkthrough
  overlap with the standard factory demo; reuse framing but re-capture with the
  local-model config so the run is internally consistent.
- Reference, do not re-record: the BYO-Ollama post and RFC-0014 are the written
  backup for anyone who wants the mechanism in detail.

## Proof takeaway

Data residency demonstrated rather than promised: on a self-hosted deployment with
a local model, the coding and verify stages completed with the managed inference
APIs provably unreachable, so the prompts and source could not have crossed the
perimeter. That is a measurement, and it is the thing to hand an auditor - it ties
into the compliance program (Factory#310) as evidence rather than a claim on a
slide.

Two honesty guardrails when you present it:

- The control was demonstrated on demand, not found switched on. The fleet's own
  build pods have no egress policy yet (Factory#462). Say "here is the control,
  and here is it working" - not "this is how your builds run today".
- The governed-cloud half of the story is not yet backed by a deployment
  (Factory#463). Lead with the local path, which is measured, and describe the
  cloud path as roadmap.

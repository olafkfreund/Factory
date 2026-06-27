---
layout: post
title: "Bring your own Ollama: running Factory builds on your own models through a Cloudflare Tunnel"
subtitle: "A remote user wants the Factory to code with the 70B model sitting on their own workstation — not our hosted providers, not an API bill. The honest answer is that you cannot connect a laptop to a cloud agent directly, and WebMCP is the wrong tool. But there is a real, scriptable pattern: expose your local Ollama through an outbound Cloudflare Tunnel and hand the Factory the HTTPS URL. Here is the full automation, why it fits our architecture with no infra change, and an even-handed case for when you should and should not do it."
date: 2026-06-14 09:00:00 +0000
author: Olaf Freund
---

A question came up that is worth answering in public, because the obvious
framing is wrong and the correct answer is more interesting: **can a remote
user run Factory builds on their own local Ollama instance and their own
downloaded models?**

The intuition is "let me connect my local Ollama to your site." That is not how
the data flows, and chasing it leads people toward things like WebMCP that do
not solve the problem. This post walks through why, then gives you a complete,
scripted, production-shaped way to actually do it with a Cloudflare Tunnel — and
an honest account of when it is a good idea and when it is not.

## The one fact that decides everything

The Factory's coding agent runs **server-side, in a pod on our cluster**. When a
build needs the model, the call goes **pod to Ollama**. It does not run in your
browser.

So for your local model to do the work, **our pod has to reach your Ollama** —
and your Ollama is listening on `localhost:11434` on a machine behind your home
or office NAT. There is no inbound path to a laptop. The fact that your browser
can reach your own `localhost` is irrelevant, because the agent is not in your
browser.

That also kills two tempting non-answers:

- **"Connect your local engine to the site" directly** — there is nothing to
  connect to; the agent is not client-side and your machine is not reachable.
- **WebMCP** — it is a real and useful draft standard, but it points the other
  way: it lets a *website* expose tools to an agent running *in the browser*. It
  does not give our server-side agent a channel through your browser to your
  Ollama, and our agent loop runs for minutes, not in a tab that can be closed.
  Wrong shape. Skip it for this.

What is left is the pattern every comparable product actually uses (Cursor tells
users to expose localhost with a tunnel; LibreChat, Open WebUI and Jan all
require one): **you publish your local Ollama as a public HTTPS endpoint through
an outbound tunnel, and the Factory calls that URL.**

## Why a tunnel fits the Factory with zero infra change

Our build pods run under a strict egress network policy. They are allowed to
reach **port 443 to any public address** (with RFC1918 private ranges blocked),
plus DNS. Nothing else — not port `11434`, not a private LAN IP.

That constraint is exactly why a tunnel works and a raw endpoint does not. A
Cloudflare Tunnel terminates TLS at Cloudflare's edge and gives you a
`https://...` hostname on **443**. Our pod can reach that today, unchanged. A
bare `http://your-laptop:11434` or a LAN address cannot leave the cluster.

It is also the same mechanism we already run our own services on — the cockpit
lives behind a `cfargotunnel.com` CNAME. Nothing exotic here.

## The real-life scenario

Maya is a platform engineer. She has a workstation with a big GPU and a Qwen
coder model she has been happy with, and a strict rule that her company's code
does not get sent to a third-party inference API. She wants the Factory's plan,
build and verify loop, but she wants the *coding* to happen on her model, on her
hardware, on her premises.

She does not want to babysit it either — she wants to run one command, get a
URL, paste it into the Factory once, and have it survive a reboot.

Below is exactly that, in two tiers: a sixty-second ephemeral trial, and a
stable named tunnel for real use.

## Tier 1: the sixty-second trial (no Cloudflare account)

This uses Cloudflare's ephemeral `trycloudflare.com` tunnel. It is perfect for
proving the round trip before committing to anything. The URL is random and
disappears when you stop the process.

```bash
#!/usr/bin/env bash
# byo-ollama-quick.sh - expose a local Ollama to the Factory via an ephemeral
# Cloudflare tunnel. No Cloudflare account needed. Good for a first trial only.
set -euo pipefail

PORT="${OLLAMA_PORT:-11434}"

command -v ollama     >/dev/null || { echo "Install Ollama:     https://ollama.com/download"; exit 1; }
command -v cloudflared >/dev/null || { echo "Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"; exit 1; }

# Bind Ollama to loopback only - the tunnel is the ONLY thing that reaches it.
export OLLAMA_HOST="127.0.0.1:${PORT}"
export OLLAMA_ORIGINS="*"
pgrep -x ollama >/dev/null || { ollama serve >/tmp/ollama.log 2>&1 & }

# Wait for the model server to answer.
until curl -fsS "http://127.0.0.1:${PORT}/api/tags" >/dev/null 2>&1; do sleep 1; done
echo "Ollama is up on 127.0.0.1:${PORT}"

# Start the ephemeral tunnel and scrape the public URL it prints.
: > /tmp/cf.log
cloudflared tunnel --url "http://127.0.0.1:${PORT}" >/tmp/cf.log 2>&1 &
url=""
for _ in $(seq 1 30); do
  url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cf.log | head -1) || true
  [ -n "$url" ] && break
  sleep 1
done
[ -n "$url" ] || { echo "Tunnel did not come up; see /tmp/cf.log"; exit 1; }

echo
echo "Paste this into the Factory as your Ollama endpoint:"
echo "  $url"
echo
echo "Verify it from the outside:"
echo "  curl -fsS $url/api/tags | head"
```

Run it, copy the URL, paste it into your Factory Ollama setting, kick off a
build. That is the whole loop. When you are done, Ctrl-C it and the URL is gone.

## Tier 2: a stable named tunnel, scripted against the Cloudflare API

The ephemeral URL is fine for a demo and wrong for real work — it changes every
run and has no access control. For Maya's actual setup we want a fixed hostname
on her own domain, created and routed entirely through the Cloudflare API, and
**fronted by Cloudflare Access** so it is not an open inference server on the
internet.

You need: a domain already on Cloudflare, and an API token scoped to
`Account: Cloudflare Tunnel: Edit` and `Zone: DNS: Edit`.

```bash
#!/usr/bin/env bash
# byo-ollama-named.sh - a STABLE Cloudflare named tunnel for your own domain,
# created via the Cloudflare API, fronted by Cloudflare Access.
# usage: ./byo-ollama-named.sh ollama.example.com
set -euo pipefail

: "${CF_API_TOKEN:?set CF_API_TOKEN (Account: Cloudflare Tunnel:Edit, Zone: DNS:Edit)}"
: "${CF_ACCOUNT_ID:?set CF_ACCOUNT_ID}"
: "${CF_ZONE_ID:?set CF_ZONE_ID}"
HOSTNAME="${1:?usage: $0 ollama.example.com}"
PORT="${OLLAMA_PORT:-11434}"
TUNNEL_NAME="${TUNNEL_NAME:-factory-ollama}"
API="https://api.cloudflare.com/client/v4"
auth=(-H "Authorization: Bearer ${CF_API_TOKEN}" -H "Content-Type: application/json")

command -v jq >/dev/null || { echo "Install jq"; exit 1; }

# 1) Create the named tunnel (Cloudflare-managed config).
secret="$(openssl rand -base64 32)"
tunnel_id="$(curl -fsS "${auth[@]}" "${API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel" \
  --data "$(jq -n --arg n "$TUNNEL_NAME" --arg s "$secret" \
            '{name:$n, tunnel_secret:$s, config_src:"cloudflare"}')" \
  | jq -r '.result.id')"
echo "tunnel id: ${tunnel_id}"

# 2) Route the hostname to your local Ollama; everything else 404s.
curl -fsS "${auth[@]}" -X PUT \
  "${API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${tunnel_id}/configurations" \
  --data "$(jq -n --arg h "$HOSTNAME" --arg svc "http://127.0.0.1:${PORT}" \
            '{config:{ingress:[{hostname:$h, service:$svc}, {service:"http_status:404"}]}}')" \
  >/dev/null

# 3) DNS: CNAME the hostname at the tunnel (proxied/orange-cloud).
curl -fsS "${auth[@]}" -X POST "${API}/zones/${CF_ZONE_ID}/dns_records" \
  --data "$(jq -n --arg h "$HOSTNAME" --arg t "${tunnel_id}.cfargotunnel.com" \
            '{type:"CNAME", name:$h, content:$t, proxied:true}')" \
  >/dev/null || echo "DNS record may already exist - continuing"

# 4) Run Ollama (loopback) and the tunnel with its token.
token="$(curl -fsS "${auth[@]}" \
  "${API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${tunnel_id}/token" | jq -r '.result')"
export OLLAMA_HOST="127.0.0.1:${PORT}"; export OLLAMA_ORIGINS="*"
pgrep -x ollama >/dev/null || { ollama serve >/tmp/ollama.log 2>&1 & }

echo "Your stable endpoint: https://${HOSTNAME}"
echo "Now add a Cloudflare Access policy + service token for this hostname (see below),"
echo "and give the Factory the service-token headers, not just the URL."
exec cloudflared tunnel run --token "${token}"
```

Run it under a process manager so it comes back after a reboot. A minimal
`systemd` unit:

```ini
# /etc/systemd/system/factory-ollama.service
[Unit]
Description=Factory BYO-Ollama tunnel
After=network-online.target
Wants=network-online.target

[Service]
Environment=CF_API_TOKEN=...  CF_ACCOUNT_ID=...  CF_ZONE_ID=...
ExecStart=/usr/local/bin/byo-ollama-named.sh ollama.example.com
Restart=always
RestartSec=5
User=maya

[Install]
WantedBy=multi-user.target
```

### Close the open-door problem with Cloudflare Access

Ollama has **no authentication of its own**. A plain tunnel means anyone who
learns the hostname can spend your GPU. Do not ship that. Put **Cloudflare
Access** in front of the hostname with a **service token**, so only a caller
presenting `CF-Access-Client-Id` and `CF-Access-Client-Secret` gets through.
The Factory then sends those headers with every request — the tunnel URL stops
being a bearer secret and becomes a properly authenticated endpoint. This is the
difference between "a script that works" and "a thing you are willing to leave
running."

## How the Factory consumes it

On our side the integration is small and already mostly in place:

- You register your endpoint (and, with Access, the service-token headers) as a
  per-user **Ollama base URL**. The build plumbs it straight into the provider
  call as `base_url` — the agent talks to your model instead of a hosted one.
- The cockpit's usage panel treats a **tunneled, self-hosted Ollama as your own
  free compute**: it shows **tokens and time spent**, not a dollar figure. You
  are not billed and we do not invent a notional cost. That is the same
  billing-mode logic we shipped recently — `local` means GPU and wall-clock
  time, not money.
- If your tunnel drops mid-build, the call times out and the run is reported as
  **failed, not silently green** — our completion evidence gate already refuses
  to call a zero-output build a success.

## Why you would do this

- **Privacy and control.** Your code and your prompts never leave your machine's
  loopback except through your own encrypted tunnel to your own endpoint. For
  regulated or proprietary work this can be the whole reason.
- **Your models, your tuning.** Use the exact quantization, context window and
  fine-tune you have already validated, not whatever a hosted catalog offers.
- **No inference bill.** The compute is yours. With the billing panel showing
  tokens and time instead of cost, the economics are honest and visible.
- **It fits today.** No change to our egress policy, no new product surface — a
  per-user URL field and an outbound tunnel you control.

## Why you might not

Be honest with yourself before you wire this into anything that matters:

- **You are exposing an unauthenticated inference server.** Without Cloudflare
  Access (or equivalent) in front, the tunnel hostname is a free-GPU faucet for
  anyone who finds it. The Access step is not optional for real use.
- **Reliability is now your problem.** If your workstation sleeps, your home
  internet hiccups, or the tunnel process dies, the build stalls. A hosted
  provider does not have a "did your laptop go to sleep" failure mode.
- **Latency and throughput are whatever your box can do.** A parallel build that
  fans out several coding workers will queue on a single local GPU. Hosted
  providers parallelize; your desk does not.
- **It is an attack surface on our side too.** A user-supplied URL that our
  server fetches is a classic SSRF vector. We mitigate it (egress blocks private
  ranges; 443-only blocks cloud-metadata endpoints; we validate the URL), but it
  is a real cost of accepting bring-your-own endpoints, and it is why this is a
  guarded, opt-in alternative rather than the default path.
- **It is more moving parts.** Tunnel, Access policy, service token, a process
  manager, a model server — versus picking a provider in a dropdown.

## The verdict

This is an **alternative, not the default**. For most users the right answer is
the hosted providers or a subscription model — fewer parts, no uptime burden,
real parallelism. But for the Mayas of the world — privacy-bound, opinionated
about their own models, with hardware already on the desk — bringing your own
Ollama over a Cloudflare Tunnel is a genuinely good fit, it costs us nothing in
infrastructure, and as the scripts above show, it automates down to one command
and a hostname.

If you run it, run it with Cloudflare Access in front. The tunnel is the easy
part; treating an unauthenticated inference server with the seriousness it
deserves is the part that actually matters.

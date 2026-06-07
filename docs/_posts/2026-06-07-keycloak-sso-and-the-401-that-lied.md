---
layout: post
title: "Keycloak, GitHub SSO, and the 401 that lied to our faces"
subtitle: "How we gave the Factory suite a front door — and the three-headed bug that kept slamming it shut"
date: 2026-06-07
author: Olaf Freund
---

We wanted a simple thing: log into the Factory apps with our GitHub accounts, and let friends
do the same so they can kick the tyres. One login, four products, no per-app password
spreadsheet of shame. The grown-up name for "simple thing" is **single sign-on**, and the
grown-up tool is **Keycloak**.

What followed was a textbook homelab adventure: a few self-inflicted wounds, one genuinely
sneaky bug, and the special joy of an HTTP 401 that was *technically correct and completely
misleading*. Here's the honest version, because the varnished version teaches nobody anything.

## The shape of the thing

The plan was boring on purpose — boring is what you want from auth:

- **One Keycloak**, one `factory` realm, holding all users and one OIDC client per app.
- **GitHub brokered** through Keycloak. The apps never talk to GitHub directly; they only
  speak OIDC to Keycloak, and Keycloak does the GitHub dance and mints our own JWT.
- Public URLs (`aifactory.freundcloud.org.uk`, friends) via the in-cluster **Cloudflare
  tunnel**. Everything deployed by **ArgoCD** from `factory-gitops`, because clicking around
  in a cluster is how you get a cluster nobody can rebuild.

```
GitHub OAuth App  ──broker──▶  Keycloak (realm: factory)  ──OIDC cookie──▶  aifactory / pfactory / tfactory
```

Keycloak itself runs in the most homelab way imaginable: `start-dev`, embedded H2 on a PVC,
TLS terminated upstream by Cloudflare (`KC_PROXY_HEADERS=xforwarded`, `KC_HOSTNAME_STRICT=false`).
Is it production-grade? No. Does it let five friends log in with GitHub? Beautifully.

## Speed-run of the self-inflicted wounds

Before the *real* bug, we paid the traditional tariff of small, character-building mistakes.
You will recognise some of these. We are not proud. We are merely honest.

**1. The `master` realm mirage.** I tried to log in as my admin user… into the app… which
authenticates against the `factory` realm… where that admin user does not exist. Keycloak,
deadpan: `user_not_found`. The admin lives in `master`; the humans live in `factory`. Two
different worlds, one very confused operator. Lesson stitched onto a pillow: **app users and
app clients go in your app realm, never `master`.**

**2. The redirect_uri of a thousand sorrows.** GitHub's OAuth App callback URL is not the
app. It is not `realms/master`. It is, precisely and unforgivingly:

```
https://keycloak.freundcloud.org.uk/realms/factory/broker/github/endpoint
```

Get one path segment wrong and GitHub says `redirect_uri not associated` with the smug
confidence of a bouncer who has never heard of you. We got it wrong twice — bonus points for
a leftover `*.ts.net` URL from before the Cloudflare cutover, because nothing says "fun
afternoon" like a stale hostname haunting your OAuth config.

**3. Keycloak's appetite.** Gave it 1.5Gi. It OOMKilled mid-login and served a `502 Bad
Gateway`, which we briefly mistook for a tunnel problem and investigated with great energy in
entirely the wrong place. Keycloak likes ≥2Gi. Feed it.

**4. `UID` is read-only in bash.** A helper script set `UID=...` and bash recoiled like a
vampire from garlic. Renamed to `USERID`. Moving on, pretending this never happened.

All annoying, all our own fault, all fixed in an afternoon. Then came the one that earned its
own section.

## The 401 that lied

Here's the setup. After wiring OIDC into the apps, the login flow looked *perfect*:

1. Click "Sign in with SSO."
2. Off to Keycloak, then GitHub, authorise, back through Keycloak.
3. The OIDC callback fires, mints our JWT, sets it as an HttpOnly `access_token` cookie, and
   redirects you into the app.

And then… the app bounced you straight back to `/login`. No error. No drama. Just a polite,
infuriating refusal to acknowledge that you had, in fact, just logged in.

The browser's first move after landing is `GET /api/auth/me` — "hi, who am I?" — and it came
back **`401 Authentication required`**. Which is hilarious, because we had *just* set a
perfectly valid token cookie. The token was fine. The cookie was fine. The 401 was a liar.

### Head one: the backend skipped its own bouncer

The backend auth is a Starlette middleware (`TokenAuthMiddleware`) that reads the token,
validates it, and stamps `request.state.user`. Sensible. But it has a list of **public
prefixes** that skip authentication — login, register, refresh, all the `/api/auth/*`
endpoints, because those obviously can't require you to already be logged in.

Spot the problem:

```python
PUBLIC_PREFIXES = ("/api/auth/", ...)   # skip auth for everything under here
```

`/api/auth/me` starts with `/api/auth/`. So the middleware **skipped it**, never set
`request.state.user`… and then the route handler did this:

```python
async def get_current_user(request):
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, "Authentication required")   # always, for /me
```

`/api/auth/me` depended on the middleware to identify the user, while simultaneously being on
the list of routes the middleware refuses to touch. It was structurally guaranteed to 401 for
*every* real session — cookie or bearer token, didn't matter. The endpoint whose entire job is
"tell me who I am" could never, by construction, know who you are. Chef's kiss.

The fix is the textbook one: **don't let a dependency trust a middleware that's been told to
ignore its route.** `get_current_user` now resolves the token itself — `Authorization: Bearer`
header, else the `access_token` cookie — and decodes it directly:

```python
user_data = getattr(request.state, "user", None)
if user_data is None:                      # middleware skipped us — do it ourselves
    token = bearer_from_header(request) or request.cookies.get("access_token")
    if token:
        payload = _try_decode_jwt(token)   # same validator the middleware uses
        if payload:
            user_data = {"id": payload["sub"], "email": payload.get("email"), ...}
if user_data is None:
    raise HTTPException(401, "Authentication required")
```

We shipped it. Ran a headless login end-to-end. `/api/auth/me` → **200**, with the user JSON.
Victory! We told everyone. We were, regrettably, only half right.

### Head two: the frontend never even asked

Because the browser *still bounced to `/login`*. So I did the thing you should always do
sooner than you do: I opened Chrome, logged in for real, and poked the live page from the
console. The smoking gun, in one line:

```
landed=/login | SPA_check(no-cred)=200 | me(with-cred)=200 | LSkeys=[aifactory-logs,aifactory-auth]
```

Read that and weep with recognition. `/api/auth/me` returns **200**. `/api/settings` returns
**200**. The cookie works *fine* — same-origin `fetch` sends it automatically. The backend was
cured. And yet the SPA sat there on `/login` like it had seen nothing.

Why? The frontend decided "am I logged in?" like this:

```ts
checkAuth: async () => {
  const token = getAuthToken();          // reads localStorage['aifactory-token']
  if (!token) {
    set({ isAuthenticated: false });     // ← bails. never calls the backend.
    return false;
  }
  // ...validate token against the server...
}
```

See it? The SPA only believed in **localStorage** tokens. That's how the *password* login
works — it stashes a token in localStorage. But OIDC doesn't do that. OIDC's token lives in an
**HttpOnly cookie**, which JavaScript famously *cannot read* (that's the whole point — it's the
good kind of cookie). So `getAuthToken()` found nothing, and `checkAuth` gave up **without ever
asking the server** — despite the server sitting right there, cookie in hand, ready to say
"yes, that's Olaf, hi."

Two completely independent bugs, in two different languages, arranged so that fixing the first
one revealed the second while changing *zero* of the visible symptoms. The login bounced
before the backend fix. It bounced after. Same bounce, different reason. This is the kind of
thing that makes you question your career and then, eventually, your assumptions.

The frontend fix is one honest function:

```ts
checkAuth: async () => {
  const token = getAuthToken();                 // may be null for SSO — that's OK now
  const res = await fetch('/api/auth/me', {
    credentials: 'include',                      // send the cookie
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  set({ isAuthenticated: res.ok });              // let the BACKEND decide
  return res.ok;
}
```

Stop guessing from localStorage. Ask `/api/auth/me`. It already knew the answer the whole time.

### Head three: the browser was reading yesterday's newspaper

We shipped the frontend fix, rolled it out, and… the login *still* bounced. At this point you
start to wonder if the universe is personally invested in your humiliation. But the console,
ever the honest friend, told the truth in one line:

```
server_index_bundle=index-5pDlqUV9.js | loaded=index-Y3p1H88x.js
```

The server was serving the **new** SPA. The browser was running the **old** one. The fix was
sitting right there on disk in the pod, and the browser hadn't bothered to pick it up.

Why? Our static file server (Starlette's `StaticFiles`) sent `index.html` with an `ETag` and a
`Last-Modified` but **no `Cache-Control`**. When a browser sees a cacheable-looking response
with no explicit policy, it invents one — *heuristic caching* — and happily serves the old
shell for a while. The old shell references the old JS bundle by name. So every user who'd
visited before kept getting the previous build's code after an upgrade, which is a *spectacular*
way to make a deployed fix look like it never happened.

The fix is a five-line `StaticFiles` subclass:

```python
class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"   # always revalidate the shell
        elif "/assets/" in (scope.get("path") or ""):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"  # hashed → cache forever
        return response
```

`no-cache` doesn't mean "don't store it" — it means "store it, but check with the server before
reusing it." Revalidation is a cheap `304`. Meanwhile the content-hashed assets (`index-5pDlqUV9.js`)
can be cached *forever*, because if the content changes, so does the filename. The shell stays
fresh; the heavy bits stay cached. Everyone wins, nobody reads yesterday's newspaper.

Three heads. One symptom. The login bounced before the backend fix, after the backend fix,
after the frontend fix, and only stopped bouncing after the *cache* fix. Each layer was real,
independent, and invisible until the one in front of it was removed.

## What we actually learned

- **A 401 tells you "no." It does not tell you "why."** Our 401 was generated by a route
  handler that never saw the token, not by token validation. We spent real time "fixing the
  token" — the one thing that was never broken. When an error is suspiciously absolute
  ("*every* request 401s"), suspect structure, not data.
- **Middleware exclusions are sharp.** The moment you exempt a path from auth middleware, any
  dependency on that path that trusts the middleware's output is living on borrowed time.
  Resolve auth *in the dependency* if the dependency needs it.
- **HttpOnly cookies are invisible to your SPA — on purpose.** If your "are we logged in?"
  check reads localStorage, it is blind to cookie sessions. Make the server the source of
  truth: call your `/me` endpoint with `credentials: 'include'` and believe what it says.
- **Reproduce in the real environment.** The headless `curl` test passed and we declared
  victory. The browser disagreed. Ten minutes in Chrome DevTools found in one line what
  staring at code would not: the cookie was working; the SPA simply never asked.
- **Several bugs can wear one symptom.** "Login bounces to /login" had *three* unrelated
  causes — backend, frontend, and cache. Fix one, see no change, and it's tempting to conclude
  your fix was wrong. It wasn't. There were three doors locked, and you'd only found one key at
  a time. Verify each layer independently instead of judging the whole stack by the symptom.
- **Set `Cache-Control` on your SPA shell, or your next deploy is invisible.** Content-hashed
  assets can cache forever; `index.html` must `no-cache`/revalidate, or returning users keep
  running last week's JavaScript and your fixes ship into the void.

## The front door works now

`get_current_user` resolves the token (header *or* cookie). The SPA asks `/api/auth/me`
instead of rifling through localStorage. GitHub → Keycloak → land *inside* the app, across
AIFactory, PFactory, and TFactory. We filed retrospective issues in each repo so the next
person who meets this 401 finds a paper trail instead of a mystery.

If you're standing up Keycloak SSO yourself, the reproducible recipe — install, realm, clients,
the GitHub broker callback that everyone gets wrong, and app wiring — lives in the
[Keycloak SSO TechDocs](https://github.com/olafkfreund/factory-gitops/blob/main/docs/keycloak-sso.md).
Bring 2Gi of RAM and a healthy distrust of any 401 that claims to know what it's talking about.

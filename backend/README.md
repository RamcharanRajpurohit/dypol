# DyPol.ai — backend

FastAPI backend for the DyPol.ai engineering-pulse dashboard. Reads org data
via a **GitHub App** and authenticates users via **GitHub OAuth**. Multi-tenant
ready (one App, many orgs), single-process by default with a built-in
APScheduler for background jobs.

## Stack

| Concern        | Choice                                              |
|----------------|-----------------------------------------------------|
| Framework      | FastAPI (async, ORJSON responses)                   |
| HTTP client    | httpx (async, retries via tenacity)                 |
| Database       | MongoDB (Motor)                                     |
| Auth           | GitHub App + OAuth, signed-cookie sessions          |
| Background     | APScheduler (in-process)                            |
| Validation     | Pydantic v2 + pydantic-settings                     |

## Architecture, in one picture

```
                           ┌────────────────┐
   user ──"Sign in"──►     │ GitHub OAuth   │ ◄── identity only
                           └──────┬─────────┘
                                  │ user profile + orgs
                                  ▼
   user clicks "Install" ► ┌────────────────┐
                           │ GitHub App     │ ◄── installed by org admin
                           │ (your App)     │     (one-time, per org)
                           └──────┬─────────┘
                                  │ install_id
                                  ▼
   web → /api/dashboard ► ┌──────────────────┐
                          │ FastAPI backend  │
                          │  ┌─────────────┐ │
                          │  │ install     │ │ ── 50-min cached token
                          │  │ token cache │ │
                          │  │ (Mongo TTL) │ │
                          │  └──────┬──────┘ │
                          └─────────┼────────┘
                                    ▼
                              GitHub REST API
                          (15k req/hr per install)
```

**Three things to remember:**
1. The **App private key** lives only in your env. From it, the backend signs
   short JWTs that prove "I am DyPol.ai." GitHub trades each JWT for a
   short-lived **installation token** scoped to one org.
2. **Users never see tokens.** OAuth login = a signed cookie. All GitHub
   calls use the install token, server-side.
3. **Webhooks** keep Mongo fresh in real time. The 30-min reconciler
   handles anything missed during downtime.

## Setup — one-time, ~5 minutes

### 1. Register the GitHub App

Go to https://github.com/settings/apps/new (or your org's `.../organizations/<org>/settings/apps/new`).

| Field | Value |
|---|---|
| App name | `dypol-dev` (must be globally unique on GitHub) |
| Homepage URL | `http://localhost:3000` |
| Callback URL (OAuth) | `http://localhost:8000/auth/callback` |
| Setup URL (optional) | `http://localhost:3000/dashboard` |
| Webhook URL | `http://localhost:8000/webhooks/github` (use **ngrok** for local: `ngrok http 8000`, then `https://<id>.ngrok.app/webhooks/github`) |
| Webhook secret | generate any random string, save it |
| Where can it be installed? | "Any account" (so you can install on personal + orgs) |

**Permissions (Repository):**

| Permission | Access |
|---|---|
| Metadata | Read (mandatory) |
| Contents | Read |
| Pull requests | Read |
| Issues | Read |
| Actions | Read |
| Checks | Read |
| Commit statuses | Read |
| Dependabot alerts | Read (optional) |
| Code scanning alerts | Read (optional) |
| Secret scanning alerts | Read (optional) |

**Permissions (Organization):**

| Permission | Access |
|---|---|
| Members | Read |

**Account permissions (for OAuth user identity):**

| Permission | Access |
|---|---|
| Email addresses | Read |

**Webhook events** (subscribe to):
- `Installation target`, `Meta`
- `Push`, `Pull request`, `Pull request review`, `Pull request review comment`
- `Issues`, `Issue comment`
- `Check run`, `Check suite`, `Workflow run`

### 2. Collect credentials

After the App is created GitHub gives you:
- **App ID** (visible at top of App settings)
- **Client ID** (under "Client ID")
- Click "Generate a new client secret" → **Client secret**
- Click "Generate a private key" → downloads `dypol-dev.YYYY-MM-DD.private-key.pem`. Move it next to `backend/`.

### 3. Configure `.env`

```bash
cp .env.example .env
```

Fill these:
```
GITHUB_APP_ID=123456
GITHUB_APP_SLUG=dypol-dev          # the URL slug from the install URL
GITHUB_APP_CLIENT_ID=Iv1.abc123...
GITHUB_APP_CLIENT_SECRET=...
GITHUB_APP_PRIVATE_KEY_PATH=./dypol-dev.YYYY-MM-DD.private-key.pem
GITHUB_APP_WEBHOOK_SECRET=...

APP_BASE_URL=http://localhost:8000
WEB_BASE_URL=http://localhost:3000

SESSION_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
```

### 4. Run Mongo

```bash
docker run -d --name dypol-mongo -p 27017:27017 mongo:7
```

### 5. Install + run

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

OpenAPI explorer: http://localhost:8000/docs

### 6. Install the App on your org

Visit `http://localhost:8000/auth/install` (or browse to
`https://github.com/apps/<your-app-slug>/installations/new`). Pick the org,
approve the repos. Webhooks will populate the `installations` collection in
Mongo.

### 7. Sign in as a user

Visit `http://localhost:8000/auth/login`. After GitHub consent you're
redirected to `WEB_BASE_URL/dashboard` with a session cookie. The frontend
calls the backend with `credentials: include` and the cookie carries the
session.

## Endpoints

| View / purpose      | Endpoint                                  | Auth |
|---------------------|-------------------------------------------|------|
| Health              | `GET  /health`                            | public |
| Sign in             | `GET  /auth/login`                        | public |
| OAuth callback      | `GET  /auth/callback`                     | public |
| Logout              | `POST /auth/logout`                       | session |
| Whoami              | `GET  /auth/me`                           | session |
| Install App         | `GET  /auth/install`                      | public |
| Webhook receiver    | `POST /webhooks/github`                   | HMAC |
| Dashboard           | `GET  /dashboard/`                        | session + install |
| Repos list          | `GET  /repos/`                            | session + install |
| Repo detail         | `GET  /repos/{name}`                      | session + install |
| Repo PRs            | `GET  /repos/{name}/prs`                  | session + install |
| Leaderboard         | `GET  /leaderboard/?days=30`              | session + install |
| Activity            | `GET  /activity/?limit=50`                | session + install |
| Alerts              | `GET  /alerts/`                           | session + install |
| Digest              | `GET  /digest/?days=7`                    | session + install |
| Ask                 | `POST /ask/`                              | session + install |
| Org settings        | `GET  /settings/org`, `/settings/members` | session + install |

`session + install` endpoints require the user's session cookie **and** an
org. The org is auto-resolved if the user has exactly one accessible
installation; otherwise pass `?org=<login>` or `X-Org: <login>`.

## Project layout

```
app/
├── main.py                # FastAPI factory, lifespan, CORS
├── core/
│   ├── config.py          # pydantic-settings
│   ├── db.py              # Motor + index init
│   └── errors.py          # exceptions + handlers
├── auth/
│   ├── oauth.py           # GitHub OAuth helpers
│   ├── session.py         # signed-cookie sessions
│   └── deps.py            # current_user / current_install
├── clients/
│   └── github.py          # App JWT, install tokens, per-org client
├── models/
│   └── schemas.py         # Pydantic response models
├── services/              # GitHub aggregation per domain (per-install)
│   ├── repos.py / prs.py / members.py
│   ├── leaderboard.py / digest.py / ask.py
│   ├── alerts.py / activity.py
│   └── cache.py
├── routers/               # one router per view
│   ├── auth.py / webhooks.py / health.py
│   ├── dashboard.py / repos.py / leaderboard.py
│   ├── activity.py / alerts.py / digest.py
│   ├── ask.py / settings.py
└── workers/
    └── scheduler.py       # APScheduler — installation reconciler
```

## Mongo collections

| Collection         | Purpose                                                         |
|--------------------|-----------------------------------------------------------------|
| `users`            | Profile per signed-in user                                      |
| `installations`    | One row per org/account that has installed the App              |
| `install_tokens`   | Cached installation access tokens (TTL-indexed, auto-purged)    |
| `events`           | Activity feed, populated by webhooks                            |
| `repos` / `prs` / `commits` / `members` / `alerts` | Future: populated by sync worker so views read from Mongo, not GitHub |

## Caveats — known shortcuts in this first pass

- **Search-API quotas.** `leaderboard`, `digest`, `ask`, `alerts` use
  `/search/issues` and `/search/code`, capped at 30 req/min separate from
  the core 5k/hr (or 15k/hr per install) budget.
- **Per-repo loops.** `compute_leaderboard` walks up to 30 repos × N pages
  of commits per request. For larger orgs this should run as a nightly job
  that writes results to Mongo, then views read from Mongo.
- **Live reads, no Mongo cache for domain data yet.** Auth + installs are
  in Mongo; repos/PRs/etc. are still proxied live to GitHub. Wiring a sync
  worker is the next obvious step.
- **Single-process scheduler.** APScheduler runs in the API process. When
  you scale to multiple replicas, lift jobs out into a dedicated worker so
  they don't fan out N×.
- **CSRF on writes.** The only mutating endpoint right now is the webhook
  receiver (HMAC-protected) and `/auth/logout`. If you add user-mutating
  routes, add CSRF tokens or rely on `SameSite=lax` strictly.
- **Signed-cookie sessions, no server-side revoke list.** Rotating
  `SESSION_SECRET` invalidates all sessions. If you need per-user kick,
  add a Mongo `sessions` collection and check on each request.

## Going to prod (cheat sheet)

1. Buy domain. Update DNS for `app.example.com` (web) and
   `api.example.com` (this backend).
2. In `.env`: set `APP_BASE_URL=https://api.example.com`,
   `WEB_BASE_URL=https://app.example.com`, `APP_ENV=production`,
   `CORS_ORIGINS=https://app.example.com`. Cookies become `Secure`
   automatically.
3. In your GitHub App settings: update Callback URL and Webhook URL.
4. Move private key from local `.pem` to your secret store; either keep
   `GITHUB_APP_PRIVATE_KEY_PATH` pointing at a mounted secret, or set
   `GITHUB_APP_PRIVATE_KEY` from the secret manager at deploy time.
5. Put a process manager in front (`gunicorn -k uvicorn.workers.UvicornWorker -w 2`)
   behind a TLS-terminating proxy (Caddy / nginx / Cloud Run / Fly).
6. Externalize APScheduler when you scale beyond one replica.




what  about your calling agent plan bro 

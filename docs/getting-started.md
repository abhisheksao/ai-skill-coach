# Getting started

This guide takes a fresh clone to a running copy of Skill Coach. You get
the full feature set on web and Android:

- sign-in with email or Google
- the onboarding wizard and a generated learning plan
- chat and push-to-talk voice coaching in English, Hindi, Spanish, French
  and German
- check-ins, progress and the home dashboard
- cadence nudges by push notification, and session summaries the coach
  remembers
- a per-user daily LLM budget, a rate-limit queue and a kill switch
- a nightly graph export with a restore script

Everything runs on free tiers. You create your own accounts. The repo holds
no keys or endpoints.

iOS is not covered. See [iOS](#ios) at the end.

## Contents

1. [Prerequisites](#prerequisites)
2. [Create the accounts](#2-create-the-accounts)
3. [Fill in the env files](#3-fill-in-the-env-files)
4. [Run the bootstrap script](#4-run-the-bootstrap-script)
5. [Run it locally](#5-run-it-locally)
6. [Android](#6-android)
7. [Push notifications and scheduled jobs](#7-push-notifications-and-scheduled-jobs)
8. [Deploy (optional)](#8-deploy-optional)
9. [Ops workflows (optional)](#9-ops-workflows-optional)
10. [Tests](#10-tests)
11. [Paid upgrades](#paid-upgrades)

## Prerequisites

| Tool | Version | For |
|---|---|---|
| Node.js | 22 or newer | the Expo app |
| Python | 3.12 | the API |
| [uv](https://docs.astral.sh/uv/) | recent | Python deps and running the API |
| [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) | recent | pushing the Postgres migrations |
| openssl | any | generating the internal secret |
| Android Studio + JDK 17 | — | Android builds only |

## 2. Create the accounts

### Supabase (auth, transcripts, push tokens, schedules)

1. Create a project at [supabase.com](https://supabase.com). The free plan
   is enough.
2. **Authentication → Providers → Email**: on by default. For local
   testing, you can turn off "Confirm email".
3. **Authentication → Providers → Google** (optional, for Google sign-in):
   - In Google Cloud Console, create an OAuth client of type **Web
     application**.
   - Authorized redirect URI: `https://<project-ref>.supabase.co/auth/v1/callback`.
   - Paste the client ID and secret into the Supabase Google provider form.
4. **Authentication → URL Configuration**:
   - Site URL: `http://localhost:8081` (Expo's web dev server).
   - Additional redirect URLs: `skillcoach://auth-callback` (native
     deep link). Add your hosted web URL here too if you deploy one.
5. **Database → Extensions**: enable `pg_cron` and `pg_net`. The
   scheduled jobs in step 7 need both.
6. **Project Settings → API**: you need the Project URL, the `anon`
   (public) key and the `service_role` key for step 3.

### Neo4j Aura (the coaching graph)

1. Create a free instance at [neo4j.com/cloud/aura](https://neo4j.com/cloud/platform/aura-graph-database/).
2. Save the credentials file it offers. It holds the connection URI
   (`neo4j+s://<id>.databases.neo4j.io`), the user (`neo4j`) and the
   password, and Aura shows the password only once.

Aura Free pauses an instance after a few days without traffic. Graph
calls then fail until you resume it in the Aura console. The nightly
export workflow (step 9) counts as traffic and keeps the instance awake.

### Gemini (the LLM)

Create an API key in [Google AI Studio](https://aistudio.google.com/apikey).
The default model is `gemini-3.1-flash-lite`, set by `LLM_MODEL`. Free-tier
quotas change often, so check the current numbers in AI Studio. The free
tier's terms allow Google to use prompts to improve its products. Use a
paid-tier key before real users arrive (see [Paid upgrades](#paid-upgrades)).

Switching models or tiers is config only: change `LLM_MODEL` or
`GOOGLE_API_KEY`, with no code change.

### For Android push only

- A free [Expo](https://expo.dev) account. The app uses Expo's push
  service.
- A free [Firebase](https://console.firebase.google.com) project. Android
  delivers pushes through FCM.

You set these up in step 7.

## 3. Fill in the env files

Running `scripts/bootstrap.sh` creates `api/.env` and `app/.env` from the
`.env.example` files. It then stops and lists every value that is still
empty. You can also copy the files by hand first:

```bash
cp api/.env.example api/.env
cp app/.env.example app/.env
```

**`api/.env`** (never commit it):

| Key | Where it comes from |
|---|---|
| `SUPABASE_URL` | Supabase → Project Settings → API → Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | same page, `service_role` key (server-side only) |
| `SUPABASE_JWKS_URL` | `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | the Aura credentials file |
| `GOOGLE_API_KEY` | AI Studio |
| `LLM_MODEL`, `DAILY_LLM_BUDGET` | defaults are fine (50 LLM calls per user per day) |
| `CORS_ORIGINS` | comma-separated web origins allowed to call the API |
| `INTERNAL_SECRET` | the bootstrap script generates it. The scheduled jobs send it. |

**`app/.env`**:

| Key | Value |
|---|---|
| `EXPO_PUBLIC_SUPABASE_URL` | same as `SUPABASE_URL` |
| `EXPO_PUBLIC_SUPABASE_ANON_KEY` | Supabase `anon` key (safe in the client; Row Level Security protects the data) |
| `EXPO_PUBLIC_API_URL` | `http://localhost:8000` for web. A physical phone needs your machine's LAN IP, e.g. `http://192.168.1.20:8000` |
| `EXPO_PUBLIC_DELETE_ACCOUNT_URL` | the page Settings → "Delete account" opens. Keep the placeholder until you have one. |

## 4. Run the bootstrap script

```bash
supabase login            # once, if the CLI isn't logged in yet
scripts/bootstrap.sh
```

You can re-run it at any time. It does the following:

1. creates the env files and generates `INTERNAL_SECRET`
2. checks that the required values are filled in
3. installs the API and app dependencies
4. links your Supabase project and pushes `supabase/migrations/` (it asks
   for the database password on first link)
5. applies the Neo4j constraints from `api/migrations/neo4j/`

`--skip-db` skips steps 4–5. `--api-url` is covered in step 7.

## 5. Run it locally

```bash
# terminal 1: the API
cd api && uv run uvicorn skillcoach_api.main:app --reload --host 0.0.0.0

# terminal 2: the app on web
cd app && npx expo start --web
```

Open http://localhost:8081, sign up and start a skill. The wizard,
plan, chat, check-ins, progress and dashboard all work at this point.
Voice works in Chrome. Notifications and session summaries also need
step 7.

`http://localhost:8000/health` should return `{"status": "ok", ...}`.

### Alternative: run locally with Docker (no cloud accounts required)

If you have Docker installed and prefer not to create hosted accounts on Supabase and Neo4j Aura upfront, you can run both services locally on your machine:

1. **Start local Supabase** (Postgres, Auth, Kong gateway, Studio):
   ```bash
   npx supabase start
   ```
   Run `npx supabase status` to view your local `API URL` (`http://127.0.0.1:54321`), `anon key`, and `service_role key`.
   Apply database migrations:
   ```bash
   npx supabase db push
   ```

2. **Start local Neo4j**:
   ```bash
   docker run -d \
     --name skillcoach-neo4j \
     -p 7474:7474 -p 7687:7687 \
     -e NEO4J_AUTH=neo4j/password \
     neo4j:5-community
   ```

3. **Configure local env files**:
   In `api/.env`:
   ```bash
   SUPABASE_URL=http://127.0.0.1:54321
   SUPABASE_SERVICE_ROLE_KEY=<local service_role key from supabase status>
   SUPABASE_JWKS_URL=http://127.0.0.1:54321/auth/v1/.well-known/jwks.json
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=password
   GOOGLE_API_KEY=<your Gemini API key from AI Studio>
   ```

   In `app/.env`:
   ```bash
   EXPO_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
   EXPO_PUBLIC_SUPABASE_ANON_KEY=<local anon key from supabase status>
   EXPO_PUBLIC_API_URL=http://localhost:8000
   ```

4. **Initialize Neo4j schema & run**:
   Run `scripts/bootstrap.sh --skip-db` to create constraints and install dependencies, then start the API and web app as described above. Supabase Studio is available at `http://localhost:54323` and Neo4j Browser at `http://localhost:7474`.

## 6. Android

The app uses native modules (speech recognition, notifications), so it
needs a development build. Expo Go won't work.

```bash
cd app
npx expo run:android      # emulator or a USB-connected device
```

On a physical device, set `EXPO_PUBLIC_API_URL` to your machine's LAN IP,
and start the API with `--host 0.0.0.0` (as above).

`app/app.json` uses the placeholder package id `com.anonymous.skillcoach`.
Change `android.package` (and `ios.bundleIdentifier`) to your own id
before you create the Firebase app in step 7. Firebase ties
`google-services.json` to the package id.

`app.json` points `android.googleServicesFile` at `./google-services.json`,
which you create in step 7. Until you do, either finish step 7 first or
remove that line for a build without push.

## 7. Push notifications and scheduled jobs

### Push on Android

1. **Link an Expo project.** This writes `extra.eas.projectId` into
   `app.json`, which the app needs to get an Expo push token:
   ```bash
   cd app && npx eas-cli login && npx eas-cli init
   ```
2. **Firebase.** In your Firebase project, add an Android app with your
   package id. Download `google-services.json` into `app/`. The file is
   gitignored.
3. **FCM credentials for Expo.** In Firebase → Project settings → Service
   accounts, generate a private key. Then upload it as the FCM V1 key:
   ```bash
   cd app && npx eas-cli credentials   # Android → Google Service Account → FCM V1
   ```
4. Rebuild with `npx expo run:android`. Onboarding asks for notification
   permission, and the device then registers its push token with the API.

### Scheduled jobs

Two Postgres cron jobs call the API:

- **Cadence-nudge scan**: pushes to users who fall behind their plan,
  within a daytime window and a frequency cap.
- **Session summarizer**: summarizes idle conversations so the coach
  remembers them.

The jobs run inside Supabase, so the API must be reachable from the
internet. Deploy it first (step 8), or expose your local API with a
tunnel. Then:

```bash
scripts/bootstrap.sh --skip-db --api-url https://your-api.example.com
```

This writes `supabase/.temp/cron.sql` with your API URL and
`INTERNAL_SECRET` filled in. Paste it into Supabase → SQL Editor and run
it once. The deployed API must have the same `INTERNAL_SECRET`. The
template is `supabase/cron.sql.template`. Its comments show how to check
that the jobs ran.

## 8. Deploy (optional)

`render.yaml` is a [Render](https://render.com) Blueprint with two
services:

- `skillcoach-api`: the FastAPI backend
- `skillcoach-ui`: the web app as a static site

In Render, choose **New → Blueprint** and select your fork. Fill in the
secrets it prompts for, using the same values as your env files. Then:

1. Set `EXPO_PUBLIC_API_URL` on the UI service to the API's URL.
2. Set `CORS_ORIGINS` on the API service to include the UI's URL.
3. Add the UI's URL to Supabase's redirect URLs (step 2).

Both services default to Render's free plan. A free web service sleeps
after about 15 minutes idle, and the next request waits up to a minute
for it to wake. That's fine for trying the app, but too slow for voice
with real users (see [Paid upgrades](#paid-upgrades)).

Any host that runs `uv sync` and `uvicorn` works for the API. Any static
host works for `npx expo export --platform web`, as long as unknown paths
fall back to `index.html`.

## 9. Ops workflows (optional)

`.github/workflows/` has CI plus three scheduled jobs. A failed run is the
alert: GitHub emails the repo owner.

| Workflow | Does | Turn on with |
|---|---|---|
| `ci.yml` | lint and tests for `api/` and `app/` | always on |
| `healthcheck.yml` | probes `/health` every 30 min | repo variable `HEALTH_URL` |
| `nightly-export.yml` | exports the graph to the private `graph-exports` Supabase bucket | repo variable `OPS_WORKFLOWS_ENABLED=true`, plus secrets `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| `spend-check.yml` | fails when today's estimated LLM spend passes a threshold | the same variable and the two Supabase secrets |

The scheduled jobs skip until you set their variable, so a fresh fork
doesn't send failure emails. Runbooks for restore, deletion and day-to-day
operations are in [`docs/runbooks/`](runbooks/).

## 10. Tests

```bash
cd api && uv run ruff check . && uv run pytest
cd app && npx tsc --noEmit && npm run lint && npm test
```

The API and app unit tests need no accounts. The end-to-end suites
(Playwright on web, Maestro on Android) run against your own Supabase
project and API:

- Playwright setup: [`app/e2e/playwright/.env.example`](../app/e2e/playwright/.env.example)
- Maestro flows: `app/.maestro/`

[`docs/testing.md`](testing.md) maps every test to the requirement it
covers.

## Paid upgrades

None of these is required to run the app. Each one matters before real
users arrive:

| Item | Cost (check current pricing) | Why |
|---|---|---|
| Always-on API host (e.g. Render Starter) | ~$7/mo | no cold starts. Voice latency depends on it. |
| Gemini paid tier | usage-based | higher quotas, and prompts are not used to train models |
| Apple Developer Program | $99/yr | iOS push, Sign in with Apple, TestFlight |
| Google Play Console | $25 once | Play internal-testing track instead of sideloading |

## iOS

The code builds for iOS. A free personal Apple team can't provision push
notifications or Sign in with Apple, so `app/package.json` leaves
`expo-notifications` and `expo-apple-authentication` out of iOS
autolinking. With a paid Apple Developer account you can remove those
exclusions and configure APNs and the Apple provider in Supabase. This
guide doesn't cover those steps, and that configuration hasn't been
validated.

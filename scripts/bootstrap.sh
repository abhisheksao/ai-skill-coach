#!/usr/bin/env bash
# One-time (and safe to re-run) setup for a fresh clone.
# See docs/getting-started.md for the accounts this expects.
#
#   scripts/bootstrap.sh                       # env files, deps, DB setup
#   scripts/bootstrap.sh --api-url https://... # also render the cron SQL
#   scripts/bootstrap.sh --skip-db             # env files + deps only
#
# Steps:
#   1. create api/.env and app/.env from the examples if missing
#   2. generate INTERNAL_SECRET in api/.env if empty
#   3. stop with a list if any required value is still empty
#   4. install deps (uv sync, npm install)
#   5. push Postgres migrations to your Supabase project (supabase CLI)
#   6. apply the Neo4j constraints (api/migrations/neo4j)
#   7. with --api-url: write supabase/.temp/cron.sql for the scheduled jobs
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_URL=""
SKIP_DB=0

while [ $# -gt 0 ]; do
  case "$1" in
    --api-url) API_URL="${2%/}"; shift 2 ;;
    --skip-db) SKIP_DB=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# Value of KEY in an env file (empty if missing).
env_get() { sed -n "s/^$2=//p" "$1" | tail -n 1 | tr -d '"'"'"; }

# Set KEY=VALUE in an env file, replacing an existing line or appending.
env_set() {
  local file="$1" key="$2" value="$3"
  if grep -q "^$key=" "$file"; then
    local tmp; tmp="$(mktemp)"
    awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' "$file" > "$tmp"
    mv "$tmp" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

say "Checking prerequisites"
for cmd in node npm uv openssl; do
  command -v "$cmd" >/dev/null || die "$cmd not found (see docs/getting-started.md#prerequisites)"
done
node_major="$(node -p 'process.versions.node.split(".")[0]')"
[ "$node_major" -ge 22 ] || die "Node 22+ required (found $(node -v))"
if [ "$SKIP_DB" -eq 0 ]; then
  command -v supabase >/dev/null || die "supabase CLI not found (or pass --skip-db)"
fi

say "Env files"
for dir in api app; do
  if [ ! -f "$ROOT/$dir/.env" ]; then
    cp "$ROOT/$dir/.env.example" "$ROOT/$dir/.env"
    echo "created $dir/.env from $dir/.env.example"
  else
    echo "$dir/.env exists, leaving it alone"
  fi
done

if [ -z "$(env_get "$ROOT/api/.env" INTERNAL_SECRET)" ]; then
  env_set "$ROOT/api/.env" INTERNAL_SECRET "$(openssl rand -hex 32)"
  echo "generated INTERNAL_SECRET in api/.env"
fi

missing=()
for key in SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWKS_URL \
           NEO4J_URI NEO4J_USER NEO4J_PASSWORD GOOGLE_API_KEY; do
  value="$(env_get "$ROOT/api/.env" "$key")"
  case "$value" in ""|*"<project>"*|*"<instance>"*) missing+=("api/.env: $key") ;; esac
done
for key in EXPO_PUBLIC_SUPABASE_URL EXPO_PUBLIC_SUPABASE_ANON_KEY EXPO_PUBLIC_API_URL; do
  value="$(env_get "$ROOT/app/.env" "$key")"
  case "$value" in ""|*"<project>"*|*"192.168.x.x"*) missing+=("app/.env: $key") ;; esac
done
if [ ${#missing[@]} -gt 0 ]; then
  printf '\nFill these in, then re-run this script:\n'
  printf '  - %s\n' "${missing[@]}"
  printf '\nWhere each value comes from: docs/getting-started.md#3-fill-in-the-env-files\n'
  exit 1
fi

say "Installing dependencies"
(cd "$ROOT/api" && uv sync)
(cd "$ROOT/app" && npm install)

if [ "$SKIP_DB" -eq 0 ]; then
  say "Supabase migrations"
  supabase_url="$(env_get "$ROOT/api/.env" SUPABASE_URL)"
  project_ref="$(printf '%s' "$supabase_url" | sed -n 's#^https://\([a-z0-9]*\)\.supabase\.co.*#\1#p')"
  [ -n "$project_ref" ] || die "could not read a project ref from SUPABASE_URL ($supabase_url)"
  # Prompts for the database password on first link; run `supabase login`
  # first if the CLI isn't authenticated yet.
  (cd "$ROOT" && supabase link --project-ref "$project_ref" && supabase db push)

  say "Neo4j constraints"
  (cd "$ROOT/api" && uv run python ../scripts/neo4j_init.py)
fi

if [ -n "$API_URL" ]; then
  say "Rendering cron SQL"
  secret="$(env_get "$ROOT/api/.env" INTERNAL_SECRET)"
  mkdir -p "$ROOT/supabase/.temp"
  sed -e "s#{{API_URL}}#$API_URL#g" -e "s#{{INTERNAL_SECRET}}#$secret#g" \
    "$ROOT/supabase/cron.sql.template" > "$ROOT/supabase/.temp/cron.sql"
  echo "wrote supabase/.temp/cron.sql (contains your secret; gitignored)"
  echo "paste it into Supabase -> SQL Editor and run it once"
  echo "the deployed API must have the same INTERNAL_SECRET"
fi

say "Done"
cat <<'EOF'
Next:
  cd api && uv run uvicorn skillcoach_api.main:app --reload --host 0.0.0.0
  cd app && npx expo start --web
EOF

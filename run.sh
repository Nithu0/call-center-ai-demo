#!/usr/bin/env bash
# Start demoen lokalt. Default = offline mock-providere (ingen nøkler/nett).
set -euo pipefail

cd "$(dirname "$0")"

# Last .env hvis den finnes (ufarlig om den mangler — defaults gjelder).
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo "Starter call-senter-AI-demo på http://${HOST}:${PORT}"
echo "DEPLOY_TARGET=${DEPLOY_TARGET:-local}  (bytt til azure for å peke på Azure-tjenester)"

exec uvicorn app.main:app --host "$HOST" --port "$PORT" --reload

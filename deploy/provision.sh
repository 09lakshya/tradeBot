#!/usr/bin/env bash
# One-command bring-up on a fresh Ubuntu cloud VM (spec §18: runs when your PC is off).
# Usage: scp the repo to the VM, then: bash deploy/provision.sh
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
fi

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example -> .env and fill secrets first."
  exit 1
fi

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
echo "Waiting for API health..."
until curl -sf http://localhost:8000/health >/dev/null; do sleep 2; done
docker compose exec -T api alembic upgrade head
echo "Trade Bot is up. API: http://<vm-ip>:8000  Frontend: http://<vm-ip>:3000"

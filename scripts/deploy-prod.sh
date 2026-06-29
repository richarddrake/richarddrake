#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${DEPLOY_PATH:?DEPLOY_PATH is required}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI is not installed on the deployment server." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is not available on the deployment server." >&2
  exit 1
fi

cd "$DEPLOY_PATH"

if [ ! -f docker-compose.prod.yml ]; then
  echo "docker-compose.prod.yml was not uploaded to $DEPLOY_PATH." >&2
  exit 1
fi

if [ -n "${GHCR_USERNAME:-}" ] && [ -n "${GHCR_TOKEN:-}" ]; then
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin
else
  echo "GHCR credentials were not provided; Docker will pull public images or use an existing registry login."
fi

export BACKEND_IMAGE
export FRONTEND_IMAGE
export IMAGE_TAG

docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker compose -f docker-compose.prod.yml ps
docker image prune -f

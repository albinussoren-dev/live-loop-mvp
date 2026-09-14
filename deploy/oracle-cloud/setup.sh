#!/usr/bin/env bash
set -euo pipefail

# Run on a fresh Ubuntu VM after SSHing into it.
# This script installs Docker, configures a persistent data directory,
# builds LoopLive, and starts the API with FFmpeg.

sudo apt-get update
sudo apt-get install -y ca-certificates curl git

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo systemctl enable --now docker
fi

sudo usermod -aG docker "$USER" || true

APP_DIR="$HOME/live-loop-mvp"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone https://github.com/albinussoren-dev/live-loop-mvp.git "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi

mkdir -p "$APP_DIR/data"

cd "$APP_DIR"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created $APP_DIR/.env — edit it with your Google OAuth and production secrets before starting."
fi

docker compose up -d --build

docker compose ps

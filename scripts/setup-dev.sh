#!/usr/bin/env bash
set -euo pipefail

echo "Installing frontend workspace dependencies..."
pnpm install

echo "Installing backend package in editable mode..."
(
  cd backend
  python -m pip install -e '.[dev]'
)

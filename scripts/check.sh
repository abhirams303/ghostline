#!/usr/bin/env bash
set -euo pipefail

echo "Running frontend lint..."
pnpm lint

echo "Running frontend build..."
pnpm build

echo "Running backend tests..."
(
  cd backend
  python -m pytest
)

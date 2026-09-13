#!/usr/bin/env bash
set -euo pipefail

BITCOIN_DATA_DIR="${BITCOIN_DATA_DIR:-/srv/bitcoin}"

echo "Bitcoin Pi Node installer"
echo "========================="
echo
echo "Data directory: $BITCOIN_DATA_DIR"
echo

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: Docker is not installed."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1 && \
   ! sudo docker compose version >/dev/null 2>&1; then
    echo "ERROR: Docker Compose is not available."
    exit 1
fi

if ! mountpoint -q "$BITCOIN_DATA_DIR"; then
    echo "WARNING: $BITCOIN_DATA_DIR is not a separate mounted filesystem."
    echo "Make sure your intended Bitcoin storage is mounted there before continuing."
    echo
fi

mkdir -p "$BITCOIN_DATA_DIR"

if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
else
    DOCKER=(sudo docker)
fi

echo "Pulling Bitcoin Core image..."
"${DOCKER[@]}" compose pull

echo "Starting Bitcoin Core..."
BITCOIN_DATA_DIR="$BITCOIN_DATA_DIR" \
"${DOCKER[@]}" compose up -d

echo
echo "Bitcoin Core started."
echo
echo "Check status with:"
echo "  ./scripts/bitcoin-status"

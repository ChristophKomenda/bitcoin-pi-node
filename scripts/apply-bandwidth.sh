#!/usr/bin/env bash
set -euo pipefail

# This script runs as root from the UUID-guarded systemd service.
# The setting is loaded by systemd from /etc/bitcoin-pi-node.env.
rate="${BITCOIN_BANDWIDTH_MBIT:-0}"
if [[ ! "$rate" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERROR: BITCOIN_BANDWIDTH_MBIT must be a nonnegative number" >&2
  exit 1
fi
if [[ "$rate" == 0 || "$rate" == 0.0 ]]; then
  echo 'Bitcoin bandwidth limit disabled.'
  exit 0
fi

script="${BITCOIN_BANDWIDTH_SCRIPT:-/usr/local/libexec/bitcoin-pi-node/bitcoin-bandwidth-limit.py}"
[[ -f "$script" ]] || { echo "ERROR: Missing bandwidth limiter: $script" >&2; exit 1; }

for _ in {1..15}; do
  if /usr/bin/docker inspect -f '{{.State.Running}}' bitcoin 2>/dev/null | grep -qx true; then
    exec /usr/bin/python3 "$script" apply --mbit "$rate"
  fi
  sleep 2
done
printf '%s\n' 'ERROR: Bitcoin container did not reach running state.' >&2
exit 1

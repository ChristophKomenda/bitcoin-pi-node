#!/usr/bin/env bash
set -euo pipefail

: "${BITCOIN_DATA_DIR:?BITCOIN_DATA_DIR is required}"
: "${BITCOIN_STORAGE_UUID:?BITCOIN_STORAGE_UUID is required}"

if [[ "$BITCOIN_DATA_DIR" != /* || "$BITCOIN_DATA_DIR" == "/" ]]; then
  echo "ERROR: Storage directory must be an absolute path other than /." >&2
  exit 1
fi

# Require an exact mount, not merely a directory contained in the root filesystem.
if ! mountpoint -q -- "$BITCOIN_DATA_DIR"; then
  echo "ERROR: $BITCOIN_DATA_DIR is not mounted; refusing to start Bitcoin Core." >&2
  exit 1
fi

source_device=$(findmnt -n -M "$BITCOIN_DATA_DIR" -o SOURCE)
actual_uuid=$(blkid -s UUID -o value -- "$source_device")
if [[ "$actual_uuid" != "$BITCOIN_STORAGE_UUID" ]]; then
  echo "ERROR: Wrong filesystem at $BITCOIN_DATA_DIR (UUID $actual_uuid). Expected $BITCOIN_STORAGE_UUID." >&2
  exit 1
fi

if [[ ! -w "$BITCOIN_DATA_DIR" ]]; then
  echo "ERROR: $BITCOIN_DATA_DIR is not writable by the service user." >&2
  exit 1
fi

echo "OK: $BITCOIN_DATA_DIR is mounted from $source_device with the expected UUID."

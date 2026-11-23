#!/usr/bin/env bash
set -euo pipefail

# Run as regular user from within the cloned repository.
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
if [[ "$repo_dir" == *$'\n'* || "$repo_dir" == *' '* ]]; then
  echo "ERROR: Please use a repository path without spaces or newlines." >&2
  exit 1
fi

for command in sudo docker findmnt mountpoint blkid systemd-escape sed install python3; do
  command -v "$command" >/dev/null || { echo "ERROR: Missing $command" >&2; exit 1; }
done

data_dir=$(cd "$repo_dir" && docker compose config --format json | python3 -c '
import json, sys
cfg = json.load(sys.stdin)
vols = cfg["services"]["bitcoin"]["volumes"]
matches = [v for v in vols if v.get("target") == "/home/bitcoin/.bitcoin" and v.get("type") == "bind"]
if len(matches) != 1:
    raise SystemExit("ERROR: Expected exactly one Bitcoin data bind mount")
print(matches[0]["source"])
')

if [[ "$data_dir" != /* || "$data_dir" == "/" ]]; then
  echo "ERROR: Invalid Bitcoin data directory $data_dir" >&2; exit 1
fi
if ! mountpoint -q -- "$data_dir"; then
  echo "ERROR: $data_dir is not a mount point. No changes made." >&2; exit 1
fi
source_device=$(findmnt -n -M "$data_dir" -o SOURCE)
uuid=$(sudo blkid -s UUID -o value -- "$source_device")
if [[ -z "$uuid" ]]; then
  echo "ERROR: Cannot read filesystem UUID." >&2; exit 1
fi
mount_unit=$(systemd-escape --path --suffix=mount "$data_dir")

printf 'Repository: %s\nStorage: %s\nDevice: %s\nUUID: %s\n' "$repo_dir" "$data_dir" "$source_device" "$uuid"

# Do not change an existing active service or restart the node automatically.
sudo install -d -m 0755 /usr/local/libexec/bitcoin-pi-node
sudo install -m 0755 "$repo_dir/scripts/check-storage.sh" /usr/local/libexec/bitcoin-pi-node/check-storage

config_tmp=$(mktemp)
trap 'rm -f "$config_tmp"' EXIT
printf 'BITCOIN_DATA_DIR=%s\nBITCOIN_STORAGE_UUID=%s\n' "$data_dir" "$uuid" > "$config_tmp"
sudo install -m 0600 "$config_tmp" /etc/bitcoin-pi-node.env

sed -e "s|@STORAGE_DIR@|$data_dir|g" \
    -e "s|@MOUNT_UNIT@|$mount_unit|g" \
    -e "s|@REPO_DIR@|$repo_dir|g" \
    "$repo_dir/systemd/bitcoin-pi-node.service.template" \
    | sudo tee /etc/systemd/system/bitcoin-pi-node.service >/dev/null

sudo systemctl daemon-reload
sudo env BITCOIN_DATA_DIR="$data_dir" BITCOIN_STORAGE_UUID="$uuid" \
    /usr/local/libexec/bitcoin-pi-node/check-storage

echo
echo 'Systemd unit installed and storage verified.'
echo 'The currently running Bitcoin node was NOT restarted.'
echo 'To activate the new ExecStartPre guard on the next controlled start:'
echo '  sudo systemctl restart bitcoin-pi-node.service'
echo 'To inspect the unit:'
echo '  systemctl cat bitcoin-pi-node.service'

# Home Assistant MQTT monitoring – V2 extension

This extension builds on the optional MQTT bridge introduced in PR #5. It does not expose Bitcoin RPC, alter Docker Compose, change systemd startup, or add remote node controls.

## New entities

The original 13 entity IDs remain unchanged. V2 adds 8 entities:

| MQTT entity suffix | HA entity type | Meaning |
| --- | --- | --- |
| `uptime_seconds` | sensor | Bitcoin Core uptime in seconds (`uptime` RPC) |
| `bytes_received_gib` | sensor | Cumulative inbound network bytes since daemon start, GiB |
| `bytes_sent_gib` | sensor | Cumulative outbound network bytes since daemon start, GiB |
| `storage_free_gib` | sensor | Free space on the configured **mounted** Bitcoin storage |
| `sync_stalled_minutes` | sensor | Time since block height last increased during initial block download |
| `low_storage` | binary_sensor | Mounted Bitcoin storage has less than threshold GiB free |
| `no_peers` | binary_sensor | No peer connections |
| `sync_stalled` | binary_sensor | Block height not increasing during IBD for threshold minutes |

Both numeric and binary entities use `expire_after` (default 300 seconds) to flag stale MQTT states as unavailable. Because MQTT retained messages can replay on HA startup, freshness is relative to the last received message, not proof of recent measurement; use a separate timestamp/watchdog for stronger freshness guarantees.

**Important:** `storage_free_gib` and `low_storage` only work if `BITCOIN_DATA_DIR` is an **exact mount point** (defaults to `/srv/bitcoin`). When the configured directory is not an exact mount point, the reported values become unknown, not a false healthy state. Setting a different data directory on the host must be reflected in `BITCOIN_DATA_DIR` in `/etc/bitcoin-pi-node/ha-mqtt.env`.

The network sensors report **cumulative** counters, not instantaneous download/upload speeds. Counters may reset when Bitcoin Core restarts. No wallet information is collected.

## Optional environment settings

Append the following keys to `/etc/bitcoin-pi-node/ha-mqtt.env` if desired:

```ini
BITCOIN_DATA_DIR=/srv/bitcoin
BITCOIN_HA_STORAGE_WARN_GIB=5
BITCOIN_HA_STALL_WARN_MINUTES=30
BITCOIN_HA_EXPIRE_AFTER=300
# Optional. Default: ~/.cache/bitcoin-pi-node/ha-telemetry.json for the service account
# BITCOIN_HA_CACHE_FILE=/home/admin/.cache/bitcoin-pi-node/ha-telemetry.json
```

The cache holds **only** last observed block height and the last advance timestamp. The bridge writes it under a user-private directory (0700) with a private file (0600). Do not put it under `/srv/bitcoin` or another mount that can disappear. The first run starts with no stall history; there is no fabricated 30-minute history.

## Upgrade / validation

After reviewing the files and updating the checkout, test on the Raspberry Pi:

```bash
cd /home/admin/bitcoin-pi-node
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/bitcoin-ha-mqtt.py
sudo systemctl start bitcoin-ha-mqtt.service
sudo journalctl -u bitcoin-ha-mqtt.service -n 60 --no-pager
```

The systemd timer from V1 can remain unchanged. If `getnettotals` or `uptime` are unavailable, the bridge reports failure and marks entities unavailable instead of inventing data. Check your Bitcoin Core version and CLI first.

## Home Assistant UI and alerts

An optional Lovelace card example is provided in [`home-assistant-dashboard.yaml`](home-assistant-dashboard.yaml). Paste the card YAML into a dashboard card editor and **adjust entity IDs** to the IDs created by your MQTT integration. No dashboard is automatically installed.

A separate automation example is included in [`home-assistant-alerts.yaml`](home-assistant-alerts.yaml). Change the `notify.mobile_app_YOUR_DEVICE` action to your real notify service before enabling. These examples are not automatically installed or triggered on upgrade.

### Operational considerations

- IBD stall detection only triggers while `initialblockdownload=true`; a synced node stops being classified as stalled.
- An offline or failed publisher will not increment its stall timer. `expire_after` makes stale entities unavailable after updates stop (subject to MQTT retained-message replay limitations).
- A node can have zero peers temporarily; `no_peers` is a diagnostic signal, not an automatic restart command.
- Low free space thresholds depend on your pruning configuration and storage size; review thresholds before enabling alerts.
- Avoid Docker socket mounts, open RPC ports, or HA shell commands to restart the Bitcoin container. With UUID-guarded systemd enabled, the guarded service remains the only lifecycle manager.

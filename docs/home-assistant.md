# Optional Home Assistant monitoring via MQTT

This integration publishes **read-only Bitcoin Core status** to Home Assistant using MQTT Discovery. Bitcoin RPC stays inside the Bitcoin container. No Docker socket is mounted into Home Assistant, no Bitcoin wallet access is required, and this integration does **not** offer start/stop/restart controls.

## Requirements

- Running Bitcoin Pi Node from this repository, on a Docker host with a working `docker exec bitcoin ...` command
- Home Assistant with its MQTT integration configured, and a reachable MQTT broker (e.g. Mosquitto)
- Python 3, Python package `paho-mqtt` version >=2.0 and <3.0 on the Bitcoin host
- A dedicated, least-privilege MQTT username and password, or another broker-approved authentication setup

## Install on your Bitcoin host

```bash
cd /home/admin/bitcoin-pi-node  # adjust to your checkout
python3 -m venv .venv
.venv/bin/pip install 'paho-mqtt>=2,<3'
sudo install -d -m 700 /etc/bitcoin-pi-node
sudo sh -c 'umask 077; printf "%s" "YOUR_MQTT_PASSWORD" > /etc/bitcoin-pi-node/mqtt-password'
sudo chmod 600 /etc/bitcoin-pi-node/mqtt-password
```

Create `/etc/bitcoin-pi-node/ha-mqtt.env` (readable by the service account) with:

```ini
MQTT_HOST=192.168.178.50
MQTT_PORT=1883
MQTT_USERNAME=bitcoin_monitor
MQTT_PASSWORD_FILE=/etc/bitcoin-pi-node/mqtt-password
# MQTT_TLS=true  # recommended for untrusted networks; needs broker TLS configured
# BITCOIN_HA_PREFIX=bitcoin_pi_node
# BITCOIN_HA_DEVICE_ID=bitcoin_pi_node
```

**Security:** Keep the password file and environment file private; never commit them. Prefer a dedicated non-root service account with Docker access only where needed. Note: Docker group access is effectively host-root access; this is why the script runs on the trusted Bitcoin host, *not* inside Home Assistant. If you run the systemd service as `admin`, make `/etc/bitcoin-pi-node/mqtt-password` readable by that account via ownership with mode 0600 (and similarly secure the env file). Never use a world-readable secret file.

Check once, using the same user that can run `docker exec bitcoin`:

```bash
set -a
source /etc/bitcoin-pi-node/ha-mqtt.env
set +a
.venv/bin/python scripts/bitcoin-ha-mqtt.py
```

After a successful run, Home Assistant's MQTT integration should discover the **Bitcoin Pi Node** device and its 13 sensors/binary sensors.

## Run periodically with systemd

Copy the sample units from `systemd/` into `/etc/systemd/system/`. Edit `User=admin`, `WorkingDirectory`, `ExecStart` and `EnvironmentFile` for your machine. The env file and password file must be readable by that account.

```bash
sudo cp systemd/bitcoin-ha-mqtt.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bitcoin-ha-mqtt.timer
systemctl list-timers bitcoin-ha-mqtt.timer
sudo journalctl -u bitcoin-ha-mqtt.service -n 30 --no-pager
```

The timer runs every minute. If Bitcoin RPC fails, the bridge publishes `offline`, so Home Assistant will mark its entities unavailable. MQTT discovery/state topics are retained. A broker outage or a stopped timer cannot publish `offline`; consider an HA freshness check if you need guaranteed stale-data detection.

## Entities and practical automations

Sensors: block height, header height, verification progress (%), peers, inbound/outbound peers, blockchain data size (GiB), prune height, chain and Bitcoin Core version. Binary sensors: initial block download, pruning enabled and synchronized.

Example automation idea: notify when the **Synchronized** binary sensor has been `off` for 30 minutes. You can also warn when the MQTT device becomes unavailable. Entity IDs depend on Home Assistant's naming and may vary; select them from the UI.

## Safe design

- The bridge calls `bitcoin-cli` inside the existing container instead of opening port 8332.
- MQTT contains operational metadata only, not wallet content or credentials.
- Home Assistant cannot execute arbitrary Bitcoin RPC calls.
- No automatic restarts are offered: the UUID-guarded systemd startup should remain the only lifecycle manager when enabled.
- If MQTT is on a different machine/network, use TLS and firewall restrictions as appropriate.

## Troubleshooting

- No device: check the broker hostname, login, MQTT Discovery configuration and systemd logs.
- Entities unavailable: run `bash scripts/bitcoin-status` and inspect the Bitcoin container. It may still be downloading or starting.
- Permissions error: make sure the service account can read both config files and invoke Docker; do not weaken permissions on credentials.
- Multiple Bitcoin nodes: use distinct `BITCOIN_HA_DEVICE_ID` **and** `BITCOIN_HA_PREFIX` for each node.

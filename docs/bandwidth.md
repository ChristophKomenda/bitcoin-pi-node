# Optional Bitcoin Node bandwidth limiting

This optional feature uses Linux traffic control (`tc`), a dedicated IFB device, and
`nsenter` to shape **only the Bitcoin Docker container's network namespace**.

## Configuration

Add to `.env` before running `bash scripts/install-systemd.sh`:

```dotenv
BITCOIN_BANDWIDTH_MBIT=5
```

- `0` (default): disabled; no `tc` rules are installed by the systemd hook.
- Positive value (e.g. `5`): cap both download **and** upload separately to approximately that many Mbit/s.
- You need Linux `iproute2` (`tc` and `ip`), `nsenter` from `util-linux`, and IFB kernel support.
- The Python script must run with root privileges; systemd runs the hook as root.
- This caps container packet traffic, not complete internet-line usage (protocol overhead).
- Incoming traffic shaping can drop packets at the network namespace boundary; TCP may retransmit.
- Bandwidth shaping does **not** limit the number of Bitcoin peers or the total daily data transfer.

To install and activate the configuration:

```bash
sudo apt-get install -y iproute2 util-linux
bash scripts/install-systemd.sh
sudo systemctl cat bitcoin-pi-node.service
# Plan a controlled Bitcoin restart when ready:
sudo systemctl restart bitcoin-pi-node.service
```

The installer copies `scripts/bitcoin-bandwidth-limit.py` and
`scripts/apply-bandwidth.sh` into `/usr/local/libexec/bitcoin-pi-node/`,
and stores the configured rate in `/etc/bitcoin-pi-node.env`.
The systemd service has a non-fatal `ExecStartPost` hook. If shaping fails,
the Bitcoin node may continue without a limit; review the journal.

## Inspect and change an active limit

```bash
sudo python3 scripts/bitcoin-bandwidth-limit.py status
sudo python3 scripts/bitcoin-bandwidth-limit.py apply --mbit 5
sudo python3 scripts/bitcoin-bandwidth-limit.py remove
sudo journalctl -u bitcoin-pi-node.service -n 40 --no-pager
```

Changing `.env` alone does not update a running service: rerun
`bash scripts/install-systemd.sh`, and then manually apply the new rate
if you do not want to restart Bitcoin. If you change the setting to `0`,
remove the old active rule explicitly with `remove`; disabling the hook does
not remove rules from an already running container.

When the Bitcoin container is restarted or recreated without systemd,
network namespace rules disappear until the limiter runs again. Prefer the
UUID-guarded `bitcoin-pi-node.service` as the **single lifecycle manager**;
set Docker's Compose restart policy to `restart: "no"` in a local override.

## Migrating from an existing manual systemd drop-in

If you previously configured
`/etc/systemd/system/bitcoin-pi-node.service.d/bandwidth.conf` with
`ExecStartPost=-/usr/local/sbin/bitcoin-bandwidth-on-start`, disable that
**old, redundant drop-in only after** the new repository service is installed
and shows the new hook:

```bash
sudo systemctl cat bitcoin-pi-node.service
sudo mv /etc/systemd/system/bitcoin-pi-node.service.d/bandwidth.conf \\
  /etc/systemd/system/bitcoin-pi-node.service.d/bandwidth.conf.disabled
sudo systemctl daemon-reload
```

Do not remove any other systemd drop-ins. This does not restart Bitcoin.

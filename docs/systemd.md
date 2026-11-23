# Safe automatic start with systemd

The optional systemd setup verifies the **filesystem UUID** before starting the Bitcoin container. This helps prevent writing blockchain data to the host root disk when removable storage is absent.

## Before installing

- Ensure the Bitcoin data directory configured in Docker Compose is an **existing mount point** (for example `/srv/bitcoin`).
- Mount it persistently via `/etc/fstab`, preferably by UUID.
- Confirm `docker compose config` succeeds and Docker is installed.
- Set `restart: "no"` for the Bitcoin service. Docker's own restart policy must not bypass the systemd guard.

## Install

From the root of the cloned repository:

```bash
bash scripts/install-systemd.sh
```

The script determines the actual Docker Compose bind-mount source, reads the UUID of its mounted filesystem, installs the UUID guard and systemd service, then validates the storage. It **does not** restart the currently running node.

To activate the new unit on a running node during a maintenance window (brief interruption):

```bash
sudo systemctl restart bitcoin-pi-node.service
sudo systemctl status bitcoin-pi-node.service --no-pager
```

## Optional bandwidth cap

Set `BITCOIN_BANDWIDTH_MBIT=5` in `.env` before installing the service to enable 5 Mbit/s shaping in both directions. The systemd `ExecStartPost` hook applies this after Docker Compose starts. Default `0` disables this feature. See [bandwidth.md](bandwidth.md).

## Verify

```bash
systemctl cat bitcoin-pi-node.service
sudo systemctl show bitcoin-pi-node.service -p ExecStartPre
sudo systemctl status bitcoin-pi-node.service --no-pager
findmnt /srv/bitcoin
bash scripts/bitcoin-status
```

## Operational precautions

- **Do not remove the microSD/SSD while Bitcoin Core is running.** A systemd mount dependency helps coordinate service shutdown but cannot make surprise removal or power loss safe.
- An `active (exited)` systemd status is normal for a `Type=oneshot` unit with `RemainAfterExit=yes`; use `docker compose ps` to inspect the actual container.
- A hardware failure, out-of-space condition, container crash, or incorrect permissions can still stop the node. This is a startup guard, not a complete health monitor.
- For automatic startup, run `sudo systemctl enable bitcoin-pi-node.service`. Verify with `systemctl is-enabled bitcoin-pi-node.service`.
- If you change storage devices or move the repository, rerun `bash scripts/install-systemd.sh` and review the generated unit before restarting.
- To roll back the service unit: restore your previous `/etc/systemd/system/bitcoin-pi-node.service` backup, run `sudo systemctl daemon-reload`, and restart the service during a maintenance window.

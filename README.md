<div align="center">

# ₿ Bitcoin Pi Node

### Run your own Bitcoin Core node on a Raspberry Pi 5

**Docker Compose · microSD / SSD / NVMe · Configurable blockchain pruning · UUID-guarded systemd startup**

A lightweight, self-hosted Bitcoin Core setup for Raspberry Pi 5. Keep control of your node, store blockchain data outside the container, and check sync progress using simple command-line tools.

[Get started](#quick-start) · [Safe auto-start](#optional-safe-autostart-with-systemd) · [Monitor](#monitor-your-node) · [Security](#security) · [Troubleshooting](#troubleshooting) · [Contribute](#contributing)

![Bitcoin](https://img.shields.io/badge/Bitcoin-Core-F7931A?style=flat-square&logo=bitcoin&logoColor=white)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-5-A22846?style=flat-square&logo=raspberrypi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)
![License](https://img.shields.io/github/license/ChristophKomenda/bitcoin-pi-node?style=flat-square)

</div>

> [!IMPORTANT]
> This repository runs a **pruned, validating Bitcoin Core node**, not a mining rig or a Bitcoin wallet. It does not generate Bitcoin or provide financial returns. Bitcoin Core itself is maintained independently of this repository.

## Why Bitcoin Pi Node?

Running a Bitcoin node lets you independently validate Bitcoin's rules instead of relying entirely on third-party infrastructure. This project packages a straightforward Docker deployment aimed at Raspberry Pi users who prefer dedicated storage and a minimal setup.

| Feature | Benefit |
| --- | --- |
| **Bitcoin Core in Docker** | Isolates the application from the host and makes lifecycle commands consistent. |
| **Pruning enabled** | Limits retained historical block data; the node still validates blocks during initial synchronization. |
| **Persistent data directory** | Keeps chain data across container recreation. |
| **P2P only published** | Exposes TCP `8333` for Bitcoin networking; does **not** publish RPC TCP `8332`. |
| **CLI helpers** | Inspect blockchain, connections and synchronization progress without typing long Docker commands. |
| **Adjustable storage path** | Configure the data directory and pruning target through `.env`. |
| **Optional guarded auto-start** | systemd validates the expected filesystem UUID before starting Docker Compose. |

### What this project does *not* include

- No web dashboard, Lightning Network, Tor integration, wallet setup or mining functionality.
- No automatic SSD partitioning, formatting, mounting or permission configuration.
- No remote RPC exposure or automated backup system.

## Requirements

- Raspberry Pi 5 with a supported 64-bit Linux operating system and working internet connection.
- Docker Engine and Docker Compose **plugin** installed (`docker compose`).
- Dedicated SSD/NVMe storage is recommended; microSD can work, but initial synchronization is slower and can cause significant flash wear.
- Enough **free** storage for the pruning target **plus** chainstate, indexes, logs and temporary overhead. The default `20000` MiB pruning setting is **not** a maximum for total disk usage.
- `git`, Bash, Python 3, and permission to run Docker commands.
- Adequate time, bandwidth and power for initial blockchain synchronization, which can take a long time on a Raspberry Pi.

> [!CAUTION]
> **Check your storage mount before installation.** The installer requires the configured Bitcoin data directory to be an existing mount point and runs preflight checks before deployment. Prepare and mount your dedicated microSD/SSD/NVMe first. Never format storage containing important data.

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/ChristophKomenda/bitcoin-pi-node.git
cd bitcoin-pi-node
```

### 2. Configure storage and pruning

```bash
cp .env.example .env
nano .env
```

The included example uses:

```dotenv
BITCOIN_DATA_DIR=/srv/bitcoin
BITCOIN_PRUNE_MIB=20000
```

- `BITCOIN_DATA_DIR`: host directory mounted into the container at `/home/bitcoin/.bitcoin`.
- `BITCOIN_PRUNE_MIB`: pruning target in MiB, not total disk consumption.

**Verify your mount** (adapt the path if you changed it):

```bash
findmnt -T /srv/bitcoin
lsblk -f
```

Confirm the path resolves to your intended disk and that ownership and permissions allow the Bitcoin container to write data there. The installer does not provision or mount the disk for you.

> **Custom path note:** The installer resolves the Bitcoin data bind-mount from the effective Docker Compose configuration, including `.env`. Confirm the resulting host path is mounted correctly before installation.

### 3. Start Bitcoin Core

After verifying your configured dedicated storage mount:

```bash
bash scripts/install.sh
```

Alternatively, after verifying that the dedicated storage exists, is mounted, and is writable, run:

```bash
docker compose pull
docker compose up -d
```

The installer performs storage and dependency checks before starting the service. It does **not** install Docker, partition or format a disk, or prepare your storage device.

### 4. Follow synchronization

```bash
docker compose logs -f bitcoin
```

Press `Ctrl+C` to stop viewing logs; this does not stop the container.

## Optional safe auto-start with systemd

The repository includes an **optional UUID-guarded systemd service** for a more reliable Raspberry Pi setup. It checks that the configured Bitcoin data directory is an exact mount point **and** belongs to the expected filesystem UUID before starting the container. This helps avoid writing blockchain data to your system drive if removable storage is missing or replaced.

**Before enabling systemd:** Mount your dedicated microSD, SSD, or NVMe at the path configured for Bitcoin Core, ideally via a UUID-based `/etc/fstab` entry. Ensure Docker Compose does **not** restart the container independently: set `restart: "no"` for the `bitcoin` service in a local Compose override. The repository's default Compose configuration still uses `restart: unless-stopped` until you override it.

```yaml
# docker-compose.override.yml (local configuration)
services:
  bitcoin:
    restart: "no"
```

Install the service after checking your Compose configuration and storage:

```bash
docker compose config --quiet
findmnt /srv/bitcoin              # adjust for your configured path
bash scripts/install-systemd.sh
sudo systemctl enable bitcoin-pi-node.service
```

The installation script derives the real bind mount from Compose, records the filesystem UUID, installs the guard, and updates the service definition. **It does not restart a running node.** To activate the new start guard, plan a controlled service restart after reviewing the unit.

```bash
sudo systemctl cat bitcoin-pi-node.service
sudo systemctl status bitcoin-pi-node.service --no-pager
# During a maintenance window only:
sudo systemctl restart bitcoin-pi-node.service
```

> [!NOTE]
> The UUID guard is a **startup safety check**, not a substitute for disk health monitoring or graceful shutdown during hardware failures. `active (exited)` is expected for this oneshot service; check `docker compose ps` for the container's actual state.

For the full setup, troubleshooting and rollback instructions, see **[Safe automatic start with systemd](docs/systemd.md)**.

## Monitor your node

The repository includes two convenience scripts:

**Human-readable status:**

```bash
bash scripts/bitcoin-status
```

The status script reports chain, block and header counts, verification progress, initial download state, prune state, data size, peer connections and Bitcoin Core version. It needs Python 3 on the host and a running `bitcoin` container with working RPC access inside the container.

**Run Bitcoin Core CLI commands:**

```bash
bash scripts/bitcoin-node-cli getblockchaininfo
bash scripts/bitcoin-node-cli getnetworkinfo
bash scripts/bitcoin-node-cli getblockcount
```

To confirm your node is synchronized, check that `initialblockdownload` is `false`, the node has caught up to the network tip, and connections are healthy. Progress approaching 100% alone is not a sufficient health check.

## Common operations

Run commands from the cloned repository directory:

| Task | Command |
| --- | --- |
| Check running containers | `docker compose ps` |
| Follow logs | `docker compose logs -f bitcoin` |
| Restart node | `docker compose restart bitcoin` |
| Stop node gracefully | `docker compose stop bitcoin` |
| Start node | `docker compose up -d` |
| View blockchain information | `bash scripts/bitcoin-node-cli getblockchaininfo` |
| View compact status | `bash scripts/bitcoin-status` |

**Updates:** Review the [official Bitcoin Core releases](https://bitcoincore.org/en/releases/) and the image tag in `docker-compose.yml` before upgrading. Make sure existing data is backed up appropriately, then update the pinned image version and run `docker compose pull` followed by `docker compose up -d`. Do not assume all upgrades or downgrades are reversible.

## Architecture

```text
                 Bitcoin P2P network
                          │
                     TCP 8333
                          │
┌───────────────────────────────────────────┐
│ Raspberry Pi 5 · Linux                    │
│                                           │
│  Docker Compose                           │
│  └─ bitcoin container                     │
│     ├─ Bitcoin Core (pinned image)        │
│     ├─ Pruning enabled                    │
│     └─ RPC used inside the container      │
│                │                          │
│          Persistent volume                │
│                ▼                          │
│  Host data dir: /srv/bitcoin              │
│  (ideally on mounted SSD/NVMe)            │
└───────────────────────────────────────────┘
```

**Default Compose configuration (without a local override):** `bitcoin/bitcoin:31.1`, `restart: unless-stopped`, `-printtoconsole=1`, `-server=1`, configurable `-prune`, TCP `8333:8333` and a persistent data bind mount. This reflects the repository configuration, not a guarantee that a particular Docker image tag is supported indefinitely.

## Security

The default Compose file publishes **only P2P TCP port `8333`**. RPC is **not** published on the host, and Bitcoin Core's cookie authentication stays within its data directory. Do not expose RPC to the public internet, commit wallet material, or publish `.cookie` files.

- Port forwarding `8333/TCP` on your router is optional for outbound node operation; inbound peers require additional network configuration.
- Treat your host, Docker daemon and storage permissions as security boundaries.
- Keep the operating system, Docker and Bitcoin Core updated after reviewing release notes.
- If you later enable wallet features, establish a separate wallet backup and key-management process.

Read [security notes](docs/security.md), [storage notes](docs/storage.md), and [systemd setup](docs/systemd.md).

## Troubleshooting

<details>
<summary><strong>Docker or Docker Compose is unavailable</strong></summary>

Check `docker --version` and `docker compose version`. Install Docker Engine and the Compose plugin using trusted distribution or Docker documentation, then verify Docker permissions.

</details>

<details>
<summary><strong>The installer reports the data directory is not a mount point</strong></summary>

Check `findmnt /srv/bitcoin` and `lsblk -f`. Confirm your dedicated storage is an exact mount point at the configured data directory. The installer refuses to proceed when the mount check fails.

</details>

<details>
<summary><strong>Bitcoin Core does not start or cannot write data</strong></summary>

Run `docker compose ps` and `docker compose logs --tail=100 bitcoin`. Check available disk space, file ownership, permissions and whether the SSD/NVMe filesystem is mounted.

</details>

<details>
<summary><strong>Status or CLI script fails</strong></summary>

Confirm the container is named `bitcoin`, is running, and has completed startup sufficiently for RPC to answer. Check `docker compose logs bitcoin`. The status helper also requires Python 3 locally.

</details>

<details>
<summary><strong>Initial synchronization is slow</strong></summary>

Initial block validation is CPU-, storage- and network-intensive. Check temperature, throttling, SSD speed, free space, logs and peer connectivity. A pruned node still needs to download and validate historical blocks during its initial sync.

</details>

## Roadmap (ideas, not implemented)

- [x] Add installer preflight checks and resolve storage paths from Compose.
- [x] Add optional systemd auto-start with filesystem UUID validation.
- [ ] Add an interactive setup wizard with safer defaults.
- [x] Add automated Compose validation and ShellCheck for all five scripts in GitHub Actions.
- [ ] Add tested installation examples and screenshots of CLI status output.
- [ ] Explore optional Home Assistant monitoring integration.

## Contributing

Bug reports, installation feedback and documentation improvements are welcome. Please [open an issue](https://github.com/ChristophKomenda/bitcoin-pi-node/issues) with your Raspberry Pi model, Linux version, relevant Docker version, a short description and **redacted** logs. Never include RPC cookies, wallet keys or credentials.

If this project helps you, consider starring the repository so others can discover it.

## License & acknowledgments

Released under the [MIT License](LICENSE). Bitcoin Core is a separate open-source project; see [Bitcoin Core](https://bitcoincore.org/) for its upstream documentation and licenses.

Built and maintained by [Christoph Komenda](https://github.com/ChristophKomenda). Not affiliated with the Bitcoin Core maintainers or the Raspberry Pi Foundation.

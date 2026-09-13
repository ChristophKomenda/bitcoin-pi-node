# Bitcoin Pi Node

A lightweight Bitcoin Core full node setup for Raspberry Pi 5 using Docker, NVMe storage and blockchain pruning.

## Features

- Bitcoin Core 31.1
- Raspberry Pi 5
- Docker Compose
- Dedicated NVMe storage
- Pruned full node
- Persistent blockchain data
- Only Bitcoin P2P port exposed
- RPC remains private
- Simple CLI and status helpers

## Architecture

```text
Raspberry Pi 5
├── Docker
│   └── Bitcoin Core 31.1
│       └── /home/bitcoin/.bitcoin
│           ↕
└── NVMe SSD
    └── /srv/bitcoin




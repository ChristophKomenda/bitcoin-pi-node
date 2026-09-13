# Security

## RPC

Bitcoin Core RPC is intentionally not published by Docker.

Only TCP port `8333` is exposed by the default Compose configuration.

Bitcoin Core's RPC cookie remains inside the node's data directory and must never be committed to Git.

## P2P

TCP port `8333` is the Bitcoin network port.

Inbound connections are optional. The node can operate with outbound connections only.

If inbound connectivity is enabled, forward only TCP `8333` to the Raspberry Pi.

## Updates

Keep the following components updated:

- Raspberry Pi operating system
- Docker Engine
- Docker Compose
- Bitcoin Core

Review release notes before upgrading Bitcoin Core.

## Secrets

Never commit:

- `.cookie`
- `.env` containing secrets
- private keys
- wallet backups
- API credentials
- SSH keys

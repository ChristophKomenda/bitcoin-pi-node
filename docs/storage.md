# Storage and mounting

Bitcoin Core retains chainstate, indexes, logs and temporary data in addition to the retained pruned blocks. The pruning limit is **not** a cap on all data usage.

## Recommended setup

Mount a dedicated NVMe or SSD filesystem under `/srv/bitcoin` (or use a subdirectory on a dedicated mount). The installer refuses to start if the selected directory does not exist, has insufficient free space, or resolves to the root filesystem by default.

Check the destination before installation:

```bash
lsblk -f
findmnt -T /srv/bitcoin
df -h /srv/bitcoin
```

Ensure the directory exists **on the intended mounted SSD**, and that its ownership permits the Bitcoin container to write there. The installer checks host-user write permission, but cannot guarantee container-user permissions.

If you deliberately use your root filesystem (not recommended), invoke the installer with `BITCOIN_ALLOW_ROOT_STORAGE=1`. The space and other checks still apply.

## Custom location

Edit `.env` and set an absolute `BITCOIN_DATA_DIR` path, for example `/mnt/nvme/bitcoin`, then run `bash scripts/install.sh`. The installer reads the supported settings without executing the `.env` file as code.

Never format or repartition a drive before confirming that it contains no valuable data. Keep wallet backups separate if you later enable wallet functionality.

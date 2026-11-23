#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

# Read only the supported keys from .env; never execute .env as shell code.
read_setting() {
    local key="$1" default="$2" line value
    if [[ -f .env ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ "$line" =~ ^[[:space:]]*($key)=(.*)$ ]] || continue
            value="${BASH_REMATCH[2]}"
            value="${value%$'\r'}"
            if [[ "$value" =~ ^\"([^\"]*)\"$ || "$value" =~ ^\'([^\']*)\'$ ]]; then
                value="${BASH_REMATCH[1]}"
            fi
            printf '%s' "$value"
            return
        done < .env
    fi
    printf '%s' "$default"
}

BITCOIN_DATA_DIR="${BITCOIN_DATA_DIR:-$(read_setting BITCOIN_DATA_DIR /srv/bitcoin)}"
BITCOIN_PRUNE_MIB="${BITCOIN_PRUNE_MIB:-$(read_setting BITCOIN_PRUNE_MIB 20000)}"

info 'Bitcoin Pi Node — safe installation checks'
[[ "$BITCOIN_DATA_DIR" = /* ]] || fail 'BITCOIN_DATA_DIR must be an absolute path.'
[[ "$BITCOIN_DATA_DIR" != *$'\n'* ]] || fail 'Invalid data directory.'
[[ "$BITCOIN_PRUNE_MIB" =~ ^[0-9]+$ ]] || fail 'BITCOIN_PRUNE_MIB must be an integer.'
(( 10#$BITCOIN_PRUNE_MIB >= 550 )) || fail 'Pruning target must be at least 550 MiB.'
command -v docker >/dev/null || fail 'Docker is not installed.'
command -v findmnt >/dev/null || fail 'findmnt (util-linux) is required.'
command -v df >/dev/null || fail 'df is required.'

if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
elif command -v sudo >/dev/null && sudo -n docker info >/dev/null 2>&1; then
    DOCKER=(sudo -n docker)
else
    fail 'Cannot access Docker. Configure Docker permissions or passwordless sudo for this operation.'
fi
"${DOCKER[@]}" compose version >/dev/null 2>&1 || fail 'Docker Compose plugin is required.'

# Fail closed when the intended destination is not already mounted.
[[ -d "$BITCOIN_DATA_DIR" ]] || fail "Data directory does not exist: $BITCOIN_DATA_DIR. Mount your SSD and create the directory first."
resolved_dir="$(realpath -e -- "$BITCOIN_DATA_DIR")"
mount_target="$(findmnt -T "$resolved_dir" -no TARGET | head -n 1)"
[[ -n "$mount_target" ]] || fail 'Could not determine storage mount.'
if [[ "$mount_target" == / && "${BITCOIN_ALLOW_ROOT_STORAGE:-0}" != 1 ]]; then
    fail "Data resolves to the root filesystem. Mount dedicated storage or explicitly set BITCOIN_ALLOW_ROOT_STORAGE=1 (advanced)."
fi
[[ -w "$resolved_dir" ]] || fail 'Host user cannot write to the data directory. Check directory ownership/permissions.'

# Prune target is not total disk use: reserve 8 GiB for chainstate and overhead.
available_kib="$(df -Pk "$resolved_dir" | awk 'NR==2 {print $4}')"
[[ "$available_kib" =~ ^[0-9]+$ ]] || fail 'Could not read available disk space.'
required_kib=$(( 10#$BITCOIN_PRUNE_MIB * 1024 + 8 * 1024 * 1024 ))
(( available_kib >= required_kib )) || fail "Insufficient free storage. Need at least $((required_kib / 1024)) MiB free; available $((available_kib / 1024)) MiB."

info "Data directory: $resolved_dir"
info "Detected filesystem mount: $mount_target"
info "Pruning target: $BITCOIN_PRUNE_MIB MiB"
info "Available space: $((available_kib / 1024)) MiB"
info 'Note: container write permissions and image compatibility must still be verified during startup.'

export BITCOIN_DATA_DIR="$resolved_dir" BITCOIN_PRUNE_MIB
"${DOCKER[@]}" compose config --quiet || fail 'Compose configuration is invalid.'
"${DOCKER[@]}" compose pull
"${DOCKER[@]}" compose up -d
info 'Node started. Inspect logs: docker compose logs -f bitcoin'
info 'View status: bash scripts/bitcoin-status'

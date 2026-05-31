#!/usr/bin/env bash
# Contabo VPS — 8 GB RAM: no swap, dynamic paths under /opt + user fbot.
#
# One-liner (SSH as root for first install only):
#   curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/contabo-init.sh | bash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export FTB_SWAP_GB="${FTB_SWAP_GB:-0}"
exec bash "$SCRIPT_DIR/vps-init.sh"

#!/usr/bin/env bash
# Oracle Cloud Always Free — low RAM: 2G swap, same /opt layout + user fbot.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export FTB_SWAP_GB="${FTB_SWAP_GB:-2}"
exec bash "$SCRIPT_DIR/vps-init.sh"

#!/usr/bin/env bash
# Oracle Cloud wrapper — delegates to vps-init.sh (2G swap, ubuntu user).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export SWAP_GB="${SWAP_GB:-2}"
export RUN_USER="${RUN_USER:-ubuntu}"
export INSTALL_DIR="${INSTALL_DIR:-/home/ubuntu/futures-trading-bot}"
exec bash "$SCRIPT_DIR/vps-init.sh"

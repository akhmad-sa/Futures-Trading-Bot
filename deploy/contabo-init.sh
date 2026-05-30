#!/usr/bin/env bash
# Futures Trading Bot — Contabo VPS init
#
# Typical Contabo VPS (e.g. 4 vCPU / 8 GB RAM / 150 GB):
#   - Login as root
#   - Ubuntu 24.04 LTS recommended
#
# One-liner (fresh VPS):
#   curl -fsSL https://raw.githubusercontent.com/akhmad-sa/Futures-Trading-Bot/main/deploy/contabo-init.sh | bash
#
# Re-run to update from main:
#   bash /root/futures-trading-bot/deploy/contabo-init.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 8 GB RAM — no swap needed; 150 GB disk — Parquet dataset OK
export SWAP_GB="${SWAP_GB:-0}"
export RUN_USER="${RUN_USER:-root}"
export INSTALL_DIR="${INSTALL_DIR:-/root/futures-trading-bot}"
export GIT_REPO="${GIT_REPO:-https://github.com/akhmad-sa/Futures-Trading-Bot.git}"
export GIT_BRANCH="${GIT_BRANCH:-main}"

exec bash "$SCRIPT_DIR/vps-init.sh"

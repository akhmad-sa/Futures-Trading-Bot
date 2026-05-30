#!/usr/bin/env bash
# Install Futures Trading Bot systemd units (paper and/or live).
#
# Usage:
#   ./deploy/install-systemd.sh [install_dir] [linux_user] [paper|live|both]
#
# Example:
#   ./deploy/install-systemd.sh /home/ubuntu/futures-trading-bot ubuntu paper

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${1:-/home/ubuntu/futures-trading-bot}"
RUN_USER="${2:-ubuntu}"
MODE="${3:-paper}"

if [[ ! -f "$INSTALL_DIR/main.py" ]]; then
  echo "Error: $INSTALL_DIR/main.py not found. Set install_dir to your clone path." >&2
  exit 1
fi

if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
  echo "Error: $INSTALL_DIR/venv/bin/python not found. Create venv first." >&2
  exit 1
fi

render_unit() {
  local src="$1"
  local dest="$2"
  sed "s|@INSTALL_DIR@|$INSTALL_DIR|g; s|@USER@|$RUN_USER|g" "$src" | sudo tee "$dest" > /dev/null
}

install_paper() {
  render_unit \
    "$SCRIPT_DIR/systemd/futures-trading-bot-paper.service" \
    "/etc/systemd/system/futures-trading-bot-paper.service"
  sudo systemctl daemon-reload
  echo "Installed futures-trading-bot-paper.service"
  echo "  sudo systemctl enable --now futures-trading-bot-paper"
  echo "  journalctl -u futures-trading-bot-paper -f"
}

install_live() {
  render_unit \
    "$SCRIPT_DIR/systemd/futures-trading-bot-live.service" \
    "/etc/systemd/system/futures-trading-bot-live.service"
  sudo systemctl daemon-reload
  echo "Installed futures-trading-bot-live.service"
  echo "  sudo systemctl enable --now futures-trading-bot-live"
  echo "  journalctl -u futures-trading-bot-live -f"
}

case "$MODE" in
  paper) install_paper ;;
  live) install_live ;;
  both) install_paper; install_live ;;
  *)
    echo "Usage: $0 [install_dir] [user] [paper|live|both]" >&2
    exit 1
    ;;
esac

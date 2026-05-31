#!/usr/bin/env bash
# Install Futures Trading Bot systemd units (paper and/or live).
#
# Reads paths from deploy/lib/defaults.sh or /etc/futures-trading-bot/env
#
# Usage:
#   sudo ./deploy/install-systemd.sh [install_dir] [service_user] [paper|live|both|telegram|all]
#
# Example (defaults):
#   sudo ./deploy/install-systemd.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/defaults.sh"

INSTALL_DIR="${1:-$FTB_INSTALL_DIR}"
RUN_USER="${2:-$FTB_SERVICE_USER}"
MODE="${3:-paper}"

if [[ ! -f "$INSTALL_DIR/main.py" ]]; then
  echo "Error: $INSTALL_DIR/main.py not found." >&2
  exit 1
fi

if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
  echo "Error: $INSTALL_DIR/venv/bin/python not found. Run vps-init.sh first." >&2
  exit 1
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

render_unit() {
  local src="$1"
  local dest="$2"
  sed "s|@INSTALL_DIR@|$INSTALL_DIR|g; s|@USER@|$RUN_USER|g" "$src" | tee "$dest" > /dev/null
}

install_paper() {
  render_unit \
    "$SCRIPT_DIR/systemd/futures-trading-bot-paper.service" \
    "/etc/systemd/system/futures-trading-bot-paper.service"
  systemctl daemon-reload
  echo "Installed futures-trading-bot-paper.service"
  echo "  User=$RUN_USER  WorkingDirectory=$INSTALL_DIR"
  echo "  sudo systemctl enable --now futures-trading-bot-paper"
}

install_live() {
  render_unit \
    "$SCRIPT_DIR/systemd/futures-trading-bot-live.service" \
    "/etc/systemd/system/futures-trading-bot-live.service"
  systemctl daemon-reload
  echo "Installed futures-trading-bot-live.service"
  echo "  User=$RUN_USER  WorkingDirectory=$INSTALL_DIR"
  echo "  sudo systemctl enable --now futures-trading-bot-live"
}

install_telegram() {
  render_unit \
    "$SCRIPT_DIR/systemd/futures-trading-bot-telegram.service" \
    "/etc/systemd/system/futures-trading-bot-telegram.service"
  if [[ -f "$SCRIPT_DIR/sudoers/futures-trading-bot-telegram" ]]; then
    sed "s|@USER@|$RUN_USER|g" "$SCRIPT_DIR/sudoers/futures-trading-bot-telegram" \
      > "/etc/sudoers.d/futures-trading-bot-telegram"
    chmod 440 "/etc/sudoers.d/futures-trading-bot-telegram"
    visudo -cf "/etc/sudoers.d/futures-trading-bot-telegram"
    echo "Installed sudoers.d/futures-trading-bot-telegram"
  fi
  systemctl daemon-reload
  echo "Installed futures-trading-bot-telegram.service"
  echo "  User=$RUN_USER  WorkingDirectory=$INSTALL_DIR"
  echo "  Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env"
  echo "  sudo systemctl enable --now futures-trading-bot-telegram"
}

case "$MODE" in
  paper) install_paper ;;
  live) install_live ;;
  both) install_paper; install_live ;;
  telegram) install_telegram ;;
  all) install_paper; install_live; install_telegram ;;
  *)
    echo "Usage: $0 [install_dir] [service_user] [paper|live|both|telegram|all]" >&2
    exit 1
    ;;
esac

#!/usr/bin/env bash
# Shared deploy paths — source from init/install scripts (do not execute directly).
#
# Override on the VPS (first file found wins):
#   /etc/futures-trading-bot/env
#   deploy/deploy.env  (next to this repo)

DEPLOY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$DEPLOY_LIB_DIR")"

for _ftb_env in /etc/futures-trading-bot/env "$DEPLOY_DIR/deploy.env"; do
  if [[ -f "$_ftb_env" ]]; then
    # shellcheck disable=SC1090
    source "$_ftb_env"
    break
  fi
done
unset _ftb_env

PROJECT_SLUG="${PROJECT_SLUG:-futures-trading-bot}"

# Service account (never root)
FTB_SERVICE_USER="${FTB_SERVICE_USER:-${RUN_USER:-fbot}}"
# Application tree (FHS — not /root or user home)
FTB_INSTALL_DIR="${FTB_INSTALL_DIR:-${INSTALL_DIR:-/opt/${PROJECT_SLUG}}}"
FTB_LOG_DIR="${FTB_LOG_DIR:-/var/log/${PROJECT_SLUG}}"
FTB_STATE_DIR="${FTB_STATE_DIR:-/var/lib/${PROJECT_SLUG}}"
FTB_SWAP_GB="${FTB_SWAP_GB:-${SWAP_GB:-0}}"

# Backward-compatible aliases
RUN_USER="$FTB_SERVICE_USER"
INSTALL_DIR="$FTB_INSTALL_DIR"
SWAP_GB="$FTB_SWAP_GB"
LOG="${LOG:-${FTB_LOG_DIR}/init.log}"
SETUP_NOTES="${FTB_INSTALL_DIR}/deploy/SETUP-NOTES.txt"

ftb_require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run as root: sudo bash deploy/vps-init.sh" >&2
    exit 1
  fi
}

ftb_ensure_service_user() {
  if id "$FTB_SERVICE_USER" &>/dev/null; then
    _ftb_add_journal_group
    return
  fi
  useradd --system \
    --home-dir "$FTB_STATE_DIR" \
    --create-home \
    --shell /bin/bash \
    "$FTB_SERVICE_USER"
  _ftb_add_journal_group
}

_ftb_add_journal_group() {
  if getent group systemd-journal &>/dev/null; then
    usermod -aG systemd-journal "$FTB_SERVICE_USER" 2>/dev/null || true
  fi
}

ftb_prepare_host_dirs() {
  mkdir -p "$FTB_LOG_DIR" "$FTB_STATE_DIR" "$(dirname "$FTB_INSTALL_DIR")"
  chown "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$FTB_LOG_DIR" "$FTB_STATE_DIR"
}

ftb_ensure_app_dirs() {
  mkdir -p \
    "$FTB_INSTALL_DIR/data/candles" \
    "$FTB_INSTALL_DIR/logs" \
    "$FTB_INSTALL_DIR/storage"
  ftb_fix_ownership
}

ftb_fix_ownership() {
  chown -R "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$FTB_INSTALL_DIR"
}

ftb_run_as_user() {
  sudo -u "$FTB_SERVICE_USER" bash -lc "$*"
}

ftb_print_paths() {
  echo "  FTB_SERVICE_USER=$FTB_SERVICE_USER"
  echo "  FTB_INSTALL_DIR=$FTB_INSTALL_DIR"
  echo "  FTB_LOG_DIR=$FTB_LOG_DIR"
  echo "  FTB_STATE_DIR=$FTB_STATE_DIR"
  echo "  FTB_SWAP_GB=$FTB_SWAP_GB"
}

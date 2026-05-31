#!/usr/bin/env bash
# Futures Trading Bot — generic VPS init (Ubuntu/Debian)
#
# Layout (defaults, overridable via /etc/futures-trading-bot/env):
#   user:  fbot
#   app:   /opt/futures-trading-bot
#   logs:  /var/log/futures-trading-bot
#   state: /var/lib/futures-trading-bot
#
# Usage (as root):
#   curl -fsSL .../deploy/contabo-init.sh | bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/defaults.sh"

GIT_REPO="${GIT_REPO:-https://github.com/akhmad-sa/Futures-Trading-Bot.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-}"

log() { echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"; }

setup_packages() {
  log "Installing system packages..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    git curl ca-certificates ufw sudo \
    software-properties-common \
    build-essential libffi-dev libssl-dev
}

setup_python() {
  if [[ -n "$PYTHON_BIN" ]] && command -v "$PYTHON_BIN" &>/dev/null; then
    log "Using configured Python: $PYTHON_BIN"
    return
  fi
  if command -v python3.12 &>/dev/null; then
    PYTHON_BIN=python3.12
    apt-get install -y python3.12-venv python3-pip || true
    log "Using python3.12"
    return
  fi
  log "python3.12 not found — installing via deadsnakes PPA..."
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update -y
  apt-get install -y python3.12 python3.12-venv python3-pip
  PYTHON_BIN=python3.12
}

setup_swap() {
  if [[ "$FTB_SWAP_GB" == "0" ]] || [[ -z "$FTB_SWAP_GB" ]]; then
    log "Swap skipped (FTB_SWAP_GB=0)."
    return
  fi
  if swapon --show 2>/dev/null | grep -q '/swapfile'; then
    log "Swap already enabled."
    return
  fi
  log "Creating ${FTB_SWAP_GB}G swapfile..."
  fallocate -l "${FTB_SWAP_GB}G" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
}

setup_firewall() {
  log "Configuring UFW (SSH only)..."
  ufw allow OpenSSH || true
  ufw --force enable || true
}

install_deploy_env_template() {
  mkdir -p /etc/futures-trading-bot
  if [[ ! -f /etc/futures-trading-bot/env ]]; then
    cp "$FTB_INSTALL_DIR/deploy/deploy.env.example" /etc/futures-trading-bot/env.example 2>/dev/null || \
      cp "$SCRIPT_DIR/deploy.env.example" /etc/futures-trading-bot/env.example
    log "Optional overrides: copy /etc/futures-trading-bot/env.example -> env"
  fi
}

clone_or_pull() {
  if [[ -d "$FTB_INSTALL_DIR/.git" ]]; then
    log "Updating $FTB_INSTALL_DIR..."
    ftb_run_as_user "cd '$FTB_INSTALL_DIR' && git fetch origin && git checkout '$GIT_BRANCH' && git pull --ff-only origin '$GIT_BRANCH'"
    return
  fi
  if [[ -d "$FTB_INSTALL_DIR" ]] && [[ -n "$(ls -A "$FTB_INSTALL_DIR" 2>/dev/null)" ]]; then
    log "ERROR: $FTB_INSTALL_DIR exists and is not a git repo — set FTB_INSTALL_DIR or remove the directory."
    exit 1
  fi
  log "Cloning $GIT_REPO ($GIT_BRANCH) -> $FTB_INSTALL_DIR..."
  ftb_run_as_user "git clone --branch '$GIT_BRANCH' --depth 1 '$GIT_REPO' '$FTB_INSTALL_DIR'"
}

setup_venv() {
  log "Creating venv ($PYTHON_BIN) and installing requirements..."
  ftb_run_as_user "cd '$FTB_INSTALL_DIR' && $PYTHON_BIN -m venv venv"
  ftb_run_as_user "cd '$FTB_INSTALL_DIR' && ./venv/bin/pip install --upgrade pip"
  ftb_run_as_user "cd '$FTB_INSTALL_DIR' && ./venv/bin/pip install -r requirements.txt"
}

setup_env_file() {
  if [[ ! -f "$FTB_INSTALL_DIR/.env" ]]; then
    log "Creating .env from .env.example..."
    ftb_run_as_user "cp '$FTB_INSTALL_DIR/.env.example' '$FTB_INSTALL_DIR/.env'"
    chmod 600 "$FTB_INSTALL_DIR/.env"
    chown "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$FTB_INSTALL_DIR/.env"
  else
    log ".env exists — unchanged."
  fi
}

install_systemd_unit() {
  log "Installing systemd unit (paper, not auto-started)..."
  chmod +x "$FTB_INSTALL_DIR/deploy/install-systemd.sh"
  "$FTB_INSTALL_DIR/deploy/install-systemd.sh"
}

smoke_test() {
  log "Smoke test..."
  ftb_run_as_user "cd '$FTB_INSTALL_DIR' && ./venv/bin/pip install -r requirements.txt -q"
  ftb_run_as_user "cd '$FTB_INSTALL_DIR' && ./venv/bin/python -c 'import websockets'"
  ftb_run_as_user "cd '$FTB_INSTALL_DIR' && ./venv/bin/python main.py --version"
  ftb_run_as_user "cd '$FTB_INSTALL_DIR' && ./venv/bin/python main.py -m list --what strategies"
}

write_setup_notes() {
  mkdir -p "$(dirname "$SETUP_NOTES")"
  cat > "$SETUP_NOTES" <<EOF
Futures Trading Bot — VPS setup
Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)

Service user:  $FTB_SERVICE_USER
Install dir:   $FTB_INSTALL_DIR
Log dir:       $FTB_LOG_DIR
State dir:     $FTB_STATE_DIR
Init log:      $LOG

Optional path overrides: /etc/futures-trading-bot/env
  (see deploy/deploy.env.example)

1) Secrets:
   sudo nano $FTB_INSTALL_DIR/.env

2) Config:
   sudo nano $FTB_INSTALL_DIR/configs/strategy.env
   sudo nano $FTB_INSTALL_DIR/configs/risk.env

3) Smoke test (as service user):
   sudo -u $FTB_SERVICE_USER bash -lc 'cd $FTB_INSTALL_DIR && source venv/bin/activate && python main.py -m backtest -s trendline_breakout --symbols BTCUSDT'

4) Paper 24/7:
   sudo systemctl enable --now futures-trading-bot-paper
   journalctl -u futures-trading-bot-paper -f

5) Re-run init / update:
   sudo bash $FTB_INSTALL_DIR/deploy/vps-init.sh
   sudo bash $FTB_INSTALL_DIR/deploy/patch-update.sh
EOF
  chown "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$SETUP_NOTES"
  log "Wrote $SETUP_NOTES"
}

main() {
  ftb_require_root
  ftb_ensure_service_user
  ftb_prepare_host_dirs
  mkdir -p "$FTB_LOG_DIR"
  touch "$LOG"
  chown "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$LOG"

  exec > >(tee -a "$LOG") 2>&1

  log "=== Futures Trading Bot VPS init ==="
  ftb_print_paths | while read -r line; do log "$line"; done

  setup_packages
  setup_python
  setup_swap
  setup_firewall
  clone_or_pull
  ftb_ensure_app_dirs
  setup_venv
  setup_env_file
  install_deploy_env_template
  install_systemd_unit
  smoke_test
  write_setup_notes

  log "=== Init complete ==="
  log "Read: $SETUP_NOTES"
}

main "$@"

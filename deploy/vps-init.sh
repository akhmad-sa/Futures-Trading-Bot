#!/usr/bin/env bash
# Futures Trading Bot — generic VPS init (Ubuntu/Debian)
#
# Environment overrides:
#   INSTALL_DIR  default /root/futures-trading-bot (root) or /home/ubuntu/...
#   RUN_USER     default root if EUID=0 else ubuntu
#   GIT_REPO     default GitHub repo
#   GIT_BRANCH   default main
#   SWAP_GB      default 0 (skip). Set 1–2 on low-RAM hosts.
#
# Usage:
#   curl -fsSL .../deploy/vps-init.sh | bash          # as root (Contabo)
#   curl -fsSL .../deploy/vps-init.sh | sudo bash     # as sudo user

set -euo pipefail

GIT_REPO="${GIT_REPO:-https://github.com/akhmad-sa/Futures-Trading-Bot.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
SWAP_GB="${SWAP_GB:-0}"

if [[ -z "${RUN_USER:-}" ]]; then
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    RUN_USER=root
  else
    RUN_USER=ubuntu
  fi
fi

if [[ -z "${INSTALL_DIR:-}" ]]; then
  if [[ "$RUN_USER" == "root" ]]; then
    INSTALL_DIR="/root/futures-trading-bot"
  else
    INSTALL_DIR="/home/${RUN_USER}/futures-trading-bot"
  fi
fi

LOG="${LOG:-${INSTALL_DIR}/../futures-trading-bot-init.log}"
if [[ "$RUN_USER" == "root" ]]; then
  LOG="/root/futures-trading-bot-init.log"
fi

PYTHON_BIN="${PYTHON_BIN:-}"

log() { echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"; }

run_as_user() {
  if [[ "$RUN_USER" == "root" ]]; then
    bash -lc "$*"
  else
    sudo -u "$RUN_USER" bash -lc "$*"
  fi
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run as root: sudo bash deploy/vps-init.sh" >&2
    exit 1
  fi
}

setup_packages() {
  log "Installing system packages..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    git curl ca-certificates ufw \
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
  if [[ "$SWAP_GB" == "0" ]] || [[ -z "$SWAP_GB" ]]; then
    log "Swap skipped (SWAP_GB=0)."
    return
  fi
  if swapon --show 2>/dev/null | grep -q '/swapfile'; then
    log "Swap already enabled."
    return
  fi
  log "Creating ${SWAP_GB}G swapfile..."
  fallocate -l "${SWAP_GB}G" /swapfile
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

clone_or_pull() {
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    log "Updating $INSTALL_DIR..."
    run_as_user "cd '$INSTALL_DIR' && git fetch origin && git checkout '$GIT_BRANCH' && git pull --ff-only origin '$GIT_BRANCH'"
  else
    log "Cloning $GIT_REPO ($GIT_BRANCH) -> $INSTALL_DIR..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    run_as_user "git clone --branch '$GIT_BRANCH' --depth 1 '$GIT_REPO' '$INSTALL_DIR'"
  fi
}

setup_venv() {
  log "Creating venv ($PYTHON_BIN) and installing requirements..."
  run_as_user "cd '$INSTALL_DIR' && $PYTHON_BIN -m venv venv"
  run_as_user "cd '$INSTALL_DIR' && ./venv/bin/pip install --upgrade pip"
  run_as_user "cd '$INSTALL_DIR' && ./venv/bin/pip install -r requirements.txt"
}

setup_dirs() {
  log "Creating runtime directories..."
  run_as_user "mkdir -p '$INSTALL_DIR/data/candles' '$INSTALL_DIR/logs' '$INSTALL_DIR/storage'"
}

setup_env() {
  if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    log "Creating .env from .env.example..."
    run_as_user "cp '$INSTALL_DIR/.env.example' '$INSTALL_DIR/.env'"
  else
    log ".env exists — unchanged."
  fi
}

install_systemd_unit() {
  log "Installing systemd unit (paper, not auto-started)..."
  chmod +x "$INSTALL_DIR/deploy/install-systemd.sh"
  "$INSTALL_DIR/deploy/install-systemd.sh" "$INSTALL_DIR" "$RUN_USER" paper
}

smoke_test() {
  log "Smoke test..."
  run_as_user "cd '$INSTALL_DIR' && ./venv/bin/python main.py --version"
  run_as_user "cd '$INSTALL_DIR' && ./venv/bin/python main.py -m list --what strategies"
}

write_setup_notes() {
  local notes
  if [[ "$RUN_USER" == "root" ]]; then
    notes="/root/FUTURES-TRADING-BOT-SETUP.txt"
  else
    notes="/home/${RUN_USER}/FUTURES-TRADING-BOT-SETUP.txt"
  fi
  cat > "$notes" <<EOF
Futures Trading Bot — VPS setup notes
Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)

Install dir: $INSTALL_DIR
Init log:    $LOG
Git:         $GIT_REPO ($GIT_BRANCH)
Python:      $PYTHON_BIN

1) Secrets:
   nano $INSTALL_DIR/.env

2) Config:
   nano $INSTALL_DIR/configs/strategy.env
   nano $INSTALL_DIR/configs/risk.env
   nano $INSTALL_DIR/configs/market_structure.env

3) Backtest (portfolio — OK on 8 GB / 4 vCPU):
   cd $INSTALL_DIR && source venv/bin/activate
   python main.py -m backtest -s trendline_breakout --symbols BTCUSDT TRBUSDT DOGEUSDT

4) Paper trade foreground test:
   python main.py -m papertrade -s trendline_breakout --symbols BTCUSDT TRBUSDT

5) Paper 24/7:
   systemctl enable --now futures-trading-bot-paper
   journalctl -u futures-trading-bot-paper -f

6) Update from latest main:
   bash $INSTALL_DIR/deploy/contabo-init.sh
   # or: bash $INSTALL_DIR/deploy/vps-init.sh
EOF
  if [[ "$RUN_USER" != "root" ]]; then
    chown "${RUN_USER}:${RUN_USER}" "$notes"
  fi
  log "Wrote $notes"
}

main() {
  require_root
  touch "$LOG"
  if [[ "$RUN_USER" != "root" ]]; then
    chown "${RUN_USER}:${RUN_USER}" "$LOG" 2>/dev/null || true
  fi
  exec > >(tee -a "$LOG") 2>&1

  log "=== Futures Trading Bot VPS init ==="
  log "RUN_USER=$RUN_USER INSTALL_DIR=$INSTALL_DIR SWAP_GB=$SWAP_GB"
  setup_packages
  setup_python
  setup_swap
  setup_firewall
  clone_or_pull
  setup_venv
  setup_dirs
  setup_env
  install_systemd_unit
  smoke_test
  write_setup_notes
  log "=== Init complete ==="
  log "Read: ${RUN_USER} home FUTURES-TRADING-BOT-SETUP.txt"
}

main "$@"

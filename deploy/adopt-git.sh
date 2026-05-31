#!/usr/bin/env bash
# Attach an existing /opt/futures-trading-bot tree to GitHub (one-time).
#
# Preserves: .env, configs/, storage/, data/, venv/ (via .gitignore)
# Then you can use: sudo bash deploy/patch-update.sh
#
# Usage:
#   sudo bash /opt/futures-trading-bot/deploy/adopt-git.sh
#   curl -fsSL .../deploy/adopt-git.sh | sudo bash -s

_ftb_script="${BASH_SOURCE[0]:-}"
if [[ -n "$_ftb_script" ]] && [[ -f "$_ftb_script" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$_ftb_script")" && pwd)"
else
  SCRIPT_DIR=""
fi
unset _ftb_script

set -euo pipefail

_ftb_load_defaults() {
  local install_guess="${FTB_INSTALL_DIR:-/opt/futures-trading-bot}"
  local candidate
  for candidate in \
    "${SCRIPT_DIR:+$SCRIPT_DIR/lib/defaults.sh}" \
    "$install_guess/deploy/lib/defaults.sh"; do
    [[ -n "$candidate" && -f "$candidate" ]] || continue
    # shellcheck disable=SC1090
    source "$candidate"
    return 0
  done
  echo "Error: deploy/lib/defaults.sh not found." >&2
  exit 1
}

_ftb_load_defaults

GIT_REPO="${GIT_REPO:-https://github.com/akhmad-sa/Futures-Trading-Bot.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
INSTALL_DIR="${FTB_INSTALL_DIR:-/opt/futures-trading-bot}"

log() { echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"; }

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "$INSTALL_DIR/main.py" ]]; then
  echo "Error: $INSTALL_DIR/main.py not found." >&2
  exit 1
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
  log "$INSTALL_DIR is already a git repo."
  ftb_run_as_user "cd '$INSTALL_DIR' && git remote -v && git status -sb"
  exit 0
fi

BACKUP_DIR="${FTB_STATE_DIR}/backups/pre-git-$(date -u +%Y%m%dT%H%M%SZ)"
log "Backing up secrets and runtime data -> $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
[[ -f "$INSTALL_DIR/.env" ]] && cp -a "$INSTALL_DIR/.env" "$BACKUP_DIR/"
[[ -d "$INSTALL_DIR/configs" ]] && cp -a "$INSTALL_DIR/configs" "$BACKUP_DIR/"
[[ -d "$INSTALL_DIR/storage" ]] && cp -a "$INSTALL_DIR/storage" "$BACKUP_DIR/"
[[ -d "$INSTALL_DIR/data" ]] && cp -a "$INSTALL_DIR/data" "$BACKUP_DIR/"
chown -R "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$BACKUP_DIR"

log "Ensuring $INSTALL_DIR is owned by $FTB_SERVICE_USER (required for git)..."
chown -R "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$INSTALL_DIR"

log "Initializing git in $INSTALL_DIR (branch $GIT_BRANCH)..."
ftb_run_as_user "cd '$INSTALL_DIR' && git init -b '$GIT_BRANCH'"
ftb_run_as_user "cd '$INSTALL_DIR' && git remote add origin '$GIT_REPO'"
ftb_run_as_user "cd '$INSTALL_DIR' && git fetch --depth 1 origin '$GIT_BRANCH'"
ftb_run_as_user "cd '$INSTALL_DIR' && git checkout -f -B '$GIT_BRANCH' 'origin/$GIT_BRANCH'"

log "Restoring local .env and configs from backup..."
[[ -f "$BACKUP_DIR/.env" ]] && cp -a "$BACKUP_DIR/.env" "$INSTALL_DIR/.env"
if [[ -d "$BACKUP_DIR/configs" ]]; then
  cp -a "$BACKUP_DIR/configs/." "$INSTALL_DIR/configs/"
fi
chmod 600 "$INSTALL_DIR/.env" 2>/dev/null || true
chown -R "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$INSTALL_DIR/.env" "$INSTALL_DIR/configs"

if [[ -d "$BACKUP_DIR/storage" ]]; then
  cp -an "$BACKUP_DIR/storage/." "$INSTALL_DIR/storage/" 2>/dev/null || \
    cp -a "$BACKUP_DIR/storage/." "$INSTALL_DIR/storage/"
fi
if [[ -d "$BACKUP_DIR/data" ]]; then
  mkdir -p "$INSTALL_DIR/data"
  cp -an "$BACKUP_DIR/data/." "$INSTALL_DIR/data/" 2>/dev/null || \
    cp -a "$BACKUP_DIR/data/." "$INSTALL_DIR/data/"
fi
chown -R "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$INSTALL_DIR"

if [[ -x "$INSTALL_DIR/venv/bin/pip" ]]; then
  log "Refreshing Python dependencies..."
  ftb_run_as_user "cd '$INSTALL_DIR' && ./venv/bin/pip install -r requirements.txt -q"
else
  log "WARN: venv not found — run vps-init or create venv manually."
fi

sha="$(ftb_run_as_user "cd '$INSTALL_DIR' && git rev-parse --short HEAD")"
log "Done. Tracking origin/$GIT_BRANCH at $sha"
log "Backup: $BACKUP_DIR"
log "Next updates: sudo bash $INSTALL_DIR/deploy/patch-update.sh"

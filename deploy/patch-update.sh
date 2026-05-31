#!/usr/bin/env bash
# Futures Trading Bot — patch update (git pull, deps, optional systemd, restart).
#
# Does NOT overwrite .env or configs/*.env. Re-run vps-init only for full host setup.
#
# Usage (on VPS, as root):
#   sudo bash /opt/futures-trading-bot/deploy/patch-update.sh
#
# Options:
#   --install-dir PATH   App directory (default: FTB_INSTALL_DIR or repo root)
#   --branch NAME        Git branch (default: main or GIT_BRANCH)
#   --no-restart         Pull + pip only; leave services running
#   --restart MODE       paper | live | telegram | all | auto (default: auto)
#   --systemd MODE       Reinstall units: paper | live | telegram | all (no enable)
#   --skip-smoke         Skip post-update smoke checks
#   -h, --help           Show help
#
# Examples:
#   sudo bash deploy/patch-update.sh
#   sudo bash deploy/patch-update.sh --restart paper
#   sudo bash deploy/patch-update.sh --systemd all --restart auto

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/defaults.sh"

GIT_REPO="${GIT_REPO:-https://github.com/akhmad-sa/Futures-Trading-Bot.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"

INSTALL_DIR=""
RESTART_MODE="auto"
SYSTEMD_MODE=""
SKIP_SMOKE=0
NO_RESTART=0

PATCH_LOG="${PATCH_LOG:-${FTB_LOG_DIR}/patch.log}"

usage() {
  sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --install-dir)
      INSTALL_DIR="${2:?--install-dir requires a path}"
      shift 2
      ;;
    --branch)
      GIT_BRANCH="${2:?--branch requires a name}"
      shift 2
      ;;
    --no-restart) NO_RESTART=1; shift ;;
    --restart)
      RESTART_MODE="${2:?--restart requires paper|live|telegram|all|auto}"
      shift 2
      ;;
    --systemd)
      SYSTEMD_MODE="${2:?--systemd requires paper|live|telegram|all}"
      shift 2
      ;;
    --skip-smoke) SKIP_SMOKE=1; shift ;;
    *)
      echo "Unknown option: $1" >&2
      usage 1
      ;;
  esac
done

if [[ -z "$INSTALL_DIR" ]]; then
  if [[ -f "$FTB_INSTALL_DIR/main.py" ]]; then
    INSTALL_DIR="$FTB_INSTALL_DIR"
  elif [[ -f "$SCRIPT_DIR/../main.py" ]]; then
    INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  else
    echo "Error: cannot resolve install dir. Use --install-dir PATH" >&2
    exit 1
  fi
fi

if [[ ! -f "$INSTALL_DIR/main.py" ]]; then
  echo "Error: $INSTALL_DIR/main.py not found." >&2
  exit 1
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

mkdir -p "$FTB_LOG_DIR"
touch "$PATCH_LOG"
chown "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$PATCH_LOG" 2>/dev/null || true

exec > >(tee -a "$PATCH_LOG") 2>&1

log "=== Patch update start ==="
log "  INSTALL_DIR=$INSTALL_DIR"
log "  FTB_SERVICE_USER=$FTB_SERVICE_USER"
log "  GIT_BRANCH=$GIT_BRANCH"
log "  RESTART_MODE=$RESTART_MODE NO_RESTART=$NO_RESTART"

ftb_ensure_app_dirs

git_pull() {
  if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    log "ERROR: $INSTALL_DIR is not a git repository."
    exit 1
  fi
  log "Fetching and pulling (ff-only) branch $GIT_BRANCH..."
  ftb_run_as_user "cd '$INSTALL_DIR' && git remote -v"
  ftb_run_as_user "cd '$INSTALL_DIR' && git fetch origin '$GIT_BRANCH'"
  ftb_run_as_user "cd '$INSTALL_DIR' && git checkout '$GIT_BRANCH'"
  ftb_run_as_user "cd '$INSTALL_DIR' && git pull --ff-only origin '$GIT_BRANCH'"
  local sha
  sha="$(ftb_run_as_user "cd '$INSTALL_DIR' && git rev-parse --short HEAD")"
  log "Now at commit $sha"
}

install_requirements() {
  if [[ ! -x "$INSTALL_DIR/venv/bin/pip" ]]; then
    log "ERROR: $INSTALL_DIR/venv/bin/pip not found. Run deploy/vps-init.sh first."
    exit 1
  fi
  log "Upgrading pip and installing requirements..."
  ftb_run_as_user "cd '$INSTALL_DIR' && ./venv/bin/pip install --upgrade pip -q"
  ftb_run_as_user "cd '$INSTALL_DIR' && ./venv/bin/pip install -r requirements.txt -q"
}

merge_config_templates() {
  log "Checking for new config templates (non-destructive)..."
  if [[ -f "$INSTALL_DIR/.env.example" ]] && [[ ! -f "$INSTALL_DIR/.env" ]]; then
    log "Creating .env from .env.example..."
    ftb_run_as_user "cp '$INSTALL_DIR/.env.example' '$INSTALL_DIR/.env'"
    chmod 600 "$INSTALL_DIR/.env"
    chown "$FTB_SERVICE_USER:$FTB_SERVICE_USER" "$INSTALL_DIR/.env"
  fi
  if [[ -d "$INSTALL_DIR/configs" ]]; then
    for example in "$INSTALL_DIR/configs"/*.env.example; do
      [[ -f "$example" ]] || continue
      base="${example%.example}"
      if [[ ! -f "$base" ]]; then
        log "Adding config $(basename "$base") from example."
        ftb_run_as_user "cp '$example' '$base'"
      fi
    done
  fi
}

smoke_test() {
  if [[ "$SKIP_SMOKE" -eq 1 ]]; then
    log "Smoke tests skipped (--skip-smoke)."
    return
  fi
  log "Smoke test..."
  ftb_run_as_user "cd '$INSTALL_DIR' && ./venv/bin/python -c 'import websockets, aiohttp'"
  ftb_run_as_user "cd '$INSTALL_DIR' && ./venv/bin/python main.py --version"
  ftb_run_as_user "cd '$INSTALL_DIR' && ./venv/bin/python main.py -m list --what strategies"
  if [[ -f "$INSTALL_DIR/telegram_bot.py" ]]; then
    ftb_run_as_user "cd '$INSTALL_DIR' && ./venv/bin/python -c 'from notifier.control import TelegramControlBot'"
  fi
}

install_systemd_units() {
  local mode="$1"
  log "Refreshing systemd units (mode=$mode)..."
  chmod +x "$INSTALL_DIR/deploy/install-systemd.sh"
  "$INSTALL_DIR/deploy/install-systemd.sh" "$INSTALL_DIR" "$FTB_SERVICE_USER" "$mode"
}

unit_is_active_or_enabled() {
  local unit="$1"
  systemctl is-enabled --quiet "$unit" 2>/dev/null || \
    systemctl is-active --quiet "$unit" 2>/dev/null
}

collect_auto_restart_units() {
  local units=()
  for u in futures-trading-bot-paper futures-trading-bot-live futures-trading-bot-telegram; do
    if unit_is_active_or_enabled "$u"; then
      units+=("$u")
    fi
  done
  echo "${units[@]}"
}

restart_services() {
  if [[ "$NO_RESTART" -eq 1 ]]; then
    log "Skipping service restart (--no-restart)."
    return
  fi

  local -a units=()
  case "$RESTART_MODE" in
    auto)
      read -r -a units <<< "$(collect_auto_restart_units)"
      if [[ ${#units[@]} -eq 0 ]]; then
        log "No enabled/active bot units found — nothing to restart."
        return
      fi
      ;;
    paper) units=(futures-trading-bot-paper) ;;
    live) units=(futures-trading-bot-live) ;;
    telegram) units=(futures-trading-bot-telegram) ;;
    all)
      units=(
        futures-trading-bot-paper
        futures-trading-bot-live
        futures-trading-bot-telegram
      )
      ;;
    *)
      echo "Invalid --restart mode: $RESTART_MODE" >&2
      exit 1
      ;;
  esac

  log "Restarting: ${units[*]}"
  for unit in "${units[@]}"; do
    if systemctl cat "$unit" &>/dev/null; then
      systemctl restart "$unit" || log "WARN: restart failed for $unit"
      systemctl --no-pager status "$unit" --lines=3 || true
    else
      log "WARN: unit $unit not installed — skip"
    fi
  done
}

main() {
  git_pull
  install_requirements
  merge_config_templates

  if [[ -n "$SYSTEMD_MODE" ]]; then
    install_systemd_units "$SYSTEMD_MODE"
  fi

  smoke_test
  restart_services

  log "=== Patch update complete ==="
  log "Log file: $PATCH_LOG"
}

main "$@"

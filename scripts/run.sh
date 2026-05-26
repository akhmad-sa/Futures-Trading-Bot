#!/bin/bash

set -e

#############################################
# MULTI EXCHANGE TRADING BOT LAUNCHER
#############################################

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"
LOG_DIR="$PROJECT_ROOT/logs"
DATA_DIR="$PROJECT_ROOT/data"

mkdir -p "$LOG_DIR"
mkdir -p "$DATA_DIR"

#############################################
# DEFAULT CONFIG
#############################################

MODE="paper"
EXCHANGE="binance"
STRATEGY="example_strategy"
SYMBOL="BTC/USDT"
TIMEFRAME="1m"
ENVIRONMENT="development"

#############################################
# COLORS
#############################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

#############################################
# HELP
#############################################

show_help() {
    echo ""
    echo "========================================="
    echo " MULTI EXCHANGE TRADING BOT"
    echo "========================================="
    echo ""
    echo "Usage:"
    echo ""
    echo "  ./scripts/run.sh [OPTIONS]"
    echo ""
    echo "OPTIONS:"
    echo ""
    echo "  --mode MODE"
    echo "     live | paper | backtest"
    echo ""
    echo "  --exchange EXCHANGE"
    echo "     binance | bybit | mexc"
    echo ""
    echo "  --strategy STRATEGY"
    echo "     example_strategy"
    echo ""
    echo "  --symbol SYMBOL"
    echo "     Example: BTC/USDT"
    echo ""
    echo "  --timeframe TIMEFRAME"
    echo "     1m | 5m | 15m | 1h"
    echo ""
    echo "  --env ENVIRONMENT"
    echo "     development | staging | production"
    echo ""
    echo "  --docker"
    echo "     Run using docker compose"
    echo ""
    echo "  --monitor"
    echo "     Start monitoring service"
    echo ""
    echo "  --websocket-only"
    echo "     Run websocket engine only"
    echo ""
    echo "  --install"
    echo "     Install/update dependencies"
    echo ""
    echo "  --help"
    echo ""
    echo "Examples:"
    echo ""
    echo "  ./scripts/run.sh --mode paper --exchange binance"
    echo ""
    echo "  ./scripts/run.sh --mode live --exchange bybit --strategy example_strategy"
    echo ""
    echo "  ./scripts/run.sh --mode backtest --symbol BTC/USDT"
    echo ""
    exit 0
}

#############################################
# PARSE ARGUMENTS
#############################################

DOCKER_MODE=false
MONITOR_MODE=false
WEBSOCKET_ONLY=false
INSTALL_DEPS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)
            MODE="$2"
            shift 2
            ;;
        --exchange)
            EXCHANGE="$2"
            shift 2
            ;;
        --strategy)
            STRATEGY="$2"
            shift 2
            ;;
        --symbol)
            SYMBOL="$2"
            shift 2
            ;;
        --timeframe)
            TIMEFRAME="$2"
            shift 2
            ;;
        --env)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --docker)
            DOCKER_MODE=true
            shift
            ;;
        --monitor)
            MONITOR_MODE=true
            shift
            ;;
        --websocket-only)
            WEBSOCKET_ONLY=true
            shift
            ;;
        --install)
            INSTALL_DEPS=true
            shift
            ;;
        --help)
            show_help
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            ;;
    esac
done

#############################################
# VALIDATION
#############################################

validate_exchange() {
    case "$EXCHANGE" in
        binance|bybit|mexc)
            ;;
        *)
            echo -e "${RED}Invalid exchange: $EXCHANGE${NC}"
            exit 1
            ;;
    esac
}

validate_mode() {
    case "$MODE" in
        live|paper|backtest)
            ;;
        *)
            echo -e "${RED}Invalid mode: $MODE${NC}"
            exit 1
            ;;
    esac
}

validate_mode
validate_exchange

#############################################
# ACTIVATE VENV
#############################################

activate_venv() {
    if [ ! -d "$VENV_PATH" ]; then
        echo -e "${RED}Virtual environment not found${NC}"
        echo "Run: python3 -m venv venv"
        exit 1
    fi

    source "$VENV_PATH/bin/activate"
}

#############################################
# CHECK ENV FILE
#############################################

check_env() {
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        echo -e "${RED}.env file not found${NC}"
        exit 1
    fi
}

#############################################
# INSTALL DEPENDENCIES
#############################################

install_dependencies() {
    echo -e "${BLUE}Installing dependencies...${NC}"

    activate_venv

    pip install -r "$PROJECT_ROOT/requirements.txt"
}

#############################################
# RUN WEBSOCKET ENGINE
#############################################

run_websocket() {
    echo -e "${GREEN}Starting websocket engine...${NC}"

    activate_venv

    python "$PROJECT_ROOT/websocket/main.py" \
        --exchange "$EXCHANGE" \
        --symbol "$SYMBOL"
}

#############################################
# RUN MONITORING
#############################################

run_monitor() {
    echo -e "${GREEN}Starting monitoring service...${NC}"

    activate_venv

    python "$PROJECT_ROOT/monitoring/main.py"
}


#############################################
# RUN TRADING
#############################################

run_trading() {
    if [ "$MODE" = "live" ]; then
        echo -e "${YELLOW}WARNING: LIVE TRADING ENABLED${NC}"
        read -p "Are you sure? (yes/no): " CONFIRM
        if [ "$CONFIRM" != "yes" ]; then
            echo "Cancelled"
            exit 0
        fi
    fi

    if [ "$MODE" = "backtest" ]; then
        echo -e "${GREEN}Starting $MODE...${NC}"
    else
        echo -e "${GREEN}Starting $MODE trading...${NC}"
    fi

    activate_venv

    python "$PROJECT_ROOT/main.py" \
        --mode "$MODE" \
        --exchange "$EXCHANGE" \
        --strategy "$STRATEGY" \
        --symbol "$SYMBOL" \
        --timeframe "$TIMEFRAME"
}

#############################################
# RUN DOCKER
#############################################

run_docker() {
    echo -e "${GREEN}Starting docker services...${NC}"

    docker compose up --build
}

#############################################
# SHOW CONFIG
#############################################

show_config() {
    echo ""
    echo "========================================="
    echo " BOT CONFIGURATION"
    echo "========================================="
    echo ""
    echo "Mode        : $MODE"
    echo "Exchange    : $EXCHANGE"
    echo "Strategy    : $STRATEGY"
    echo "Symbol      : $SYMBOL"
    echo "Timeframe   : $TIMEFRAME"
    echo "Environment : $ENVIRONMENT"
    echo ""
}

#############################################
# MAIN
#############################################

main() {

    if [ "$INSTALL_DEPS" = true ]; then
        install_dependencies
        exit 0
    fi

    check_env

    show_config

    if [ "$DOCKER_MODE" = true ]; then
        run_docker
        exit 0
    fi

    if [ "$WEBSOCKET_ONLY" = true ]; then
        run_websocket
        exit 0
    fi

    if [ "$MONITOR_MODE" = true ]; then
        run_monitor
        exit 0
    fi

    case "$MODE" in
        backtest|paper|live)
            run_trading
            ;;
    esac
}

main

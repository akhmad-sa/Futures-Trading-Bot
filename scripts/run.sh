#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Default values
MODE="${1:-live}"
EXCHANGE="${2:-}"
STRATEGY="${3:-}"
SYMBOL="${4:-}"
TIMEFRAME="${5:-}"
START="${6:-}"
END="${7:-}"

# Source virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

case "$MODE" in
    live|papertrade|backtest)
        python main.py \
            --mode "$MODE" \
            ${EXCHANGE:+--exchange "$EXCHANGE"} \
            ${STRATEGY:+--strategy "$STRATEGY"} \
            ${SYMBOL:+--symbol "$SYMBOL"} \
            ${TIMEFRAME:+--timeframe "$TIMEFRAME"} \
            ${START:+--start "$START"} \
            ${END:+--end "$END"}
        ;;
    testing)
        # Run all tests
        python -m pytest tests/ -v --tb=short
        ;;
    *)
        echo "Usage: $0 {live|papertrade|backtest|testing} [exchange] [strategy] [symbol] [timeframe] [start] [end]"
        exit 1
        ;;
esac

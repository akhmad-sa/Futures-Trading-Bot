#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# ------------------------------------------------------------------
# Parse arguments
# ------------------------------------------------------------------
MODE=""
SCOPE=""
EXCHANGE=""
STRATEGY=""
SYMBOL=""
TIMEFRAME=""
START_DATE=""
END_DATE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --scope)
            if [[ -z "${2:-}" ]]; then
                echo "Error: --scope requires an argument (exchange, market_data, replay, risk, integration)"
                exit 1
            fi
            SCOPE="$2"
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
        --start)
            START_DATE="$2"
            shift 2
            ;;
        --end)
            END_DATE="$2"
            shift 2
            ;;
        -*)
            echo "Unknown option: $1"
            exit 1
            ;;
        *)
            # First non‑flag argument is the mode
            if [[ -z "$MODE" ]]; then
                MODE="$1"
                shift
            else
                echo "Unexpected argument: $1"
                exit 1
            fi
            ;;
    esac
done

# ------------------------------------------------------------------
# Validate mode
# ------------------------------------------------------------------
if [[ -z "$MODE" ]]; then
    echo "Usage: $0 {live|papertrade|backtest|testing} [options...]"
    echo ""
    echo "Common options:"
    echo "  --scope <scope>          Test scope (exchange, market_data, replay, risk, integration). Only valid with --mode testing."
    echo "  --exchange <exchange>    Exchange name (override config)."
    echo "  --strategy <strategy>    Strategy name (required for backtest)."
    echo "  --symbol <symbol>        Trading pair (required for backtest)."
    echo "  --timeframe <timeframe>  Candle timeframe."
    echo "  --start <date>           Backtest start date (YYYY-MM-DD)."
    echo "  --end <date>             Backtest end date (YYYY-MM-DD)."
    exit 1
fi

# ------------------------------------------------------------------
# Source virtual environment if it exists
# ------------------------------------------------------------------
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# ------------------------------------------------------------------
# Mode-specific execution
# ------------------------------------------------------------------
case "$MODE" in
    live|papertrade|backtest)
        python main.py \
            --mode "$MODE" \
            ${EXCHANGE:+--exchange "$EXCHANGE"} \
            ${STRATEGY:+--strategy "$STRATEGY"} \
            ${SYMBOL:+--symbol "$SYMBOL"} \
            ${TIMEFRAME:+--timeframe "$TIMEFRAME"} \
            ${START_DATE:+--start "$START_DATE"} \
            ${END_DATE:+--end "$END_DATE"}
        ;;

    testing)
        # Validate scope if provided
        VALID_SCOPES=("exchange" "market_data" "replay" "risk" "integration")
        if [[ -n "$SCOPE" ]]; then
            scope_valid=0
            for s in "${VALID_SCOPES[@]}"; do
                if [[ "$s" == "$SCOPE" ]]; then
                    scope_valid=1
                    break
                fi
            done
            if [[ $scope_valid -eq 0 ]]; then
                echo "Error: Invalid --scope '$SCOPE'. Must be one of: ${VALID_SCOPES[*]}"
                exit 1
            fi
            TEST_PATH="tests/${SCOPE}/"
        else
            TEST_PATH="tests/"
        fi

        echo "========================================"
        echo "  Running tests: $TEST_PATH"
        echo "========================================"
        python -m pytest "$TEST_PATH" -v --tb=short
        echo "========================================"
        echo "  Tests completed."
        echo "========================================"
        ;;

    *)
        echo "Error: Unknown mode '$MODE'. Use live, papertrade, backtest, or testing."
        exit 1
        ;;
esac

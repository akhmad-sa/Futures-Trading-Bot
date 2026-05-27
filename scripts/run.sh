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
SYMBOLS=()
TIMEFRAME=""
START_DATE=""
END_DATE=""

POSITIONAL=()

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
        --symbols)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                SYMBOLS+=("$1")
                shift
            done
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
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

# ------------------------------------------------------------------
# Determine mode from positional arguments
# ------------------------------------------------------------------
if [[ ${#POSITIONAL[@]} -gt 0 ]]; then
    MODE="${POSITIONAL[0]}"
    # If more than one positional argument, treat remaining as legacy positional
    if [[ "list" != "$MODE" && ${#POSITIONAL[@]} -ge 2 ]]; then
        EXCHANGE="${EXCHANGE:-${POSITIONAL[1]:-}}"
    fi
    if [[ "list" != "$MODE" && ${#POSITIONAL[@]} -ge 3 ]]; then
        STRATEGY="${STRATEGY:-${POSITIONAL[2]:-}}"
    fi
    if [[ "list" != "$MODE" && ${#POSITIONAL[@]} -ge 4 ]]; then
        SYMBOL="${SYMBOL:-${POSITIONAL[3]:-}}"
    fi
    if [[ "list" != "$MODE" && ${#POSITIONAL[@]} -ge 5 ]]; then
        TIMEFRAME="${TIMEFRAME:-${POSITIONAL[4]:-}}"
    fi
    if [[ "list" != "$MODE" && ${#POSITIONAL[@]} -ge 6 ]]; then
        START_DATE="${START_DATE:-${POSITIONAL[5]:-}}"
    fi
    if [[ "list" != "$MODE" && ${#POSITIONAL[@]} -ge 7 ]]; then
        END_DATE="${END_DATE:-${POSITIONAL[6]:-}}"
    fi
fi

# ------------------------------------------------------------------
# Validate mode
# ------------------------------------------------------------------
if [[ -z "$MODE" ]]; then
    echo "Usage: $0 {live|papertrade|backtest|testing|list} [options...]"
    echo ""
    echo "Common options:"
    echo "  --scope <scope>          Test scope (exchange, market_data, replay, risk, integration). Only valid with --mode testing."
    echo "  --exchange <exchange>    Exchange name (override config)."
    echo "  --strategy <strategy>    Strategy name (required for backtest)."
    echo "  --symbol <symbol>        Single trading pair (backward compatible)."
    echo "  --symbols <s1 s2 ...>    Space‑separated list of symbols."
    echo "  --timeframe <timeframe>  Candle timeframe."
    echo "  --start <date>           Backtest start date (YYYY-MM-DD)."
    echo "  --end <date>             Backtest end date (YYYY-MM-DD)."
    echo ""
    echo "List mode:"
    echo "  $0 list strategies"
    echo "  $0 list exchanges"
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
    list)
        # Determine what to list
        WHAT="${POSITIONAL[1]:-}"
        if [[ -z "$WHAT" ]]; then
            echo "Usage: $0 list {strategies|exchanges}"
            exit 1
        fi
        python main.py --mode list --what "$WHAT"
        ;;

    live|papertrade|backtest)
        # Build argument list for Python
        PYTHON_ARGS=( --mode "$MODE" )
        [[ -n "$EXCHANGE" ]] && PYTHON_ARGS+=( --exchange "$EXCHANGE" )
        [[ -n "$STRATEGY" ]] && PYTHON_ARGS+=( --strategy "$STRATEGY" )
        [[ -n "$SYMBOL" ]]   && PYTHON_ARGS+=( --symbol "$SYMBOL" )
        if [[ ${#SYMBOLS[@]} -gt 0 ]]; then
            PYTHON_ARGS+=( --symbols "${SYMBOLS[@]}" )
        fi
        [[ -n "$TIMEFRAME" ]] && PYTHON_ARGS+=( --timeframe "$TIMEFRAME" )
        [[ -n "$START_DATE" ]] && PYTHON_ARGS+=( --start "$START_DATE" )
        [[ -n "$END_DATE" ]]   && PYTHON_ARGS+=( --end "$END_DATE" )

        python main.py "${PYTHON_ARGS[@]}"
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
        echo "Error: Unknown mode '$MODE'. Use live, papertrade, backtest, testing, or list."
        exit 1
        ;;
esac

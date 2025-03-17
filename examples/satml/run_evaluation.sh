#!/bin/bash

# Script to run evaluations using the framework.py

# Function to display usage
show_help() {
    echo "Usage: ./run_evaluation.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help               Show this help message and exit"
    echo "  -l, --level LEVEL        Specific level IDs to evaluate (can be specified multiple times)"
    echo "  -p, --prompt PROMPT      Specific prompt IDs to evaluate (can be specified multiple times)"
    echo "  -t, --timeout TIMEOUT    Maximum time to wait for job completion (in seconds)"
    echo "  -i, --interval INTERVAL  Time between job status checks (in seconds)"
    echo ""
    echo "Examples:"
    echo "  ./run_evaluation.sh -l level1n -p urgent_action -t 600"
    echo "  ./run_evaluation.sh -l level1k level1m -p urgent_action security_alert"
}

# Default values
LEVELS=()
PROMPTS=()
TIMEOUT=300
INTERVAL=30

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        -l|--level)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
                LEVELS+=("$1")
                shift
            done
            ;;
        -p|--prompt)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
                PROMPTS+=("$1")
                shift
            done
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -i|--interval)
            INTERVAL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Build the command
CMD="python3 framework.py"

if [ ${#LEVELS[@]} -gt 0 ]; then
    CMD="$CMD --level ${LEVELS[@]}"
fi

if [ ${#PROMPTS[@]} -gt 0 ]; then
    CMD="$CMD --prompt ${PROMPTS[@]}"
fi

if [ ! -z "$TIMEOUT" ]; then
    CMD="$CMD --timeout $TIMEOUT"
fi

if [ ! -z "$INTERVAL" ]; then
    CMD="$CMD --poll-interval $INTERVAL"
fi

# Run the command
echo "Running: $CMD"
eval $CMD 
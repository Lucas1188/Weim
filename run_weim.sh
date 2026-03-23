#!/bin/bash
# ----------------------
# run_weim.sh - source-safe
# ----------------------
# Usage:
#   source ./run_weim.sh <target_binary> <timeout_per_input_sec> <max_fuzz_duration> "<harness_args>"

# ----------------------
# ARGUMENTS
# ----------------------
if [ $# -lt 4 ]; then
    echo "Usage: source $0 <target_binary> <timeout_per_input_sec> <max_fuzz_duration> \"<harness_args>\""
    # safe for sourcing
    return 1 2>/dev/null || exit 1
fi

TARGET_BIN=$1
TIMEOUT_PER_INPUT=$2
MAX_DURATION=$3
HARNESS_ARGS="$4"

# ----------------------
# EXPORT ENVIRONMENT
# ----------------------
export HARNESS_TGT="$TARGET_BIN"
export HARNESS_TIMEOUT="$TIMEOUT_PER_INPUT"
export HARNESS_ARGS="$HARNESS_ARGS"
export HARNESS_ROOT_DIR=$(pwd)

# Output dirs / files
SEEDS_DIR="$HARNESS_ROOT_DIR/seeds"
OUT_DIR="$HARNESS_ROOT_DIR/out"
LOGS_DIR="$HARNESS_ROOT_DIR/logs"
HARNESSLOG_DIR="$HARNESS_ROOT_DIR/harness_logs"
FINAL_BUGS="$HARNESS_ROOT_DIR/final_bugs.json"
ERROR_FILE="$HARNESS_ROOT_DIR/harness_error.txt"

mkdir -p "$SEEDS_DIR" "$OUT_DIR" "$LOGS_DIR"

rm -r $HARNESSLOG_DIR
rm -r $LOGS_DIR
rm -r $OUT_DIR
rm $ERROR_FILE
echo 0 > .lid
# ----------------------
# ECHO AFL COMMAND
# ----------------------
echo "[*] Environment variables set in this shell session:"
echo "HARNESS_TGT=$HARNESS_TGT"
echo "HARNESS_TIMEOUT=$HARNESS_TIMEOUT"
echo "HARNESS_ARGS=\"$HARNESS_ARGS\""
echo "HARNESS_ROOT_DIR=$HARNESS_ROOT_DIR"
echo
echo "[*] Run the following command to start AFL fuzzing manually:"
echo
echo "timeout \"$MAX_DURATION\" afl-fuzz -n -i \"$SEEDS_DIR\" -o \"$OUT_DIR\" -t \"$TIMEOUT_PER_INPUT+\" -- ./weim.py @@"
echo
echo "[*] After fuzzing, package results with:"
echo ./pack_logs.sh
echo "./hound.py" > pack_logs.sh 
echo "tar -czf \"${HARNESS_ROOT_DIR}/$(basename "$TARGET_BIN").tar.gz\" \"$OUT_DIR\" \"$HARNESSLOG_DIR\" \"$LOGS_DIR\" \"$SEEDS_DIR\" \"$FINAL_BUGS\" \"$ERROR_FILE\"" >> pack_logs.sh

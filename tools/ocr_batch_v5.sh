#!/bin/bash
# OCR batch scheduler V5 — subprocess isolation + kill -9 guarantee
# OCR 批量调度：每个 PDF 独立子进程，超时 kill -9（MuPDF 卡死唯一可靠解）
#
# Usage: ./ocr_batch_v5.sh [start_index] [count] [timeout_seconds]
set -u

START=${1:-0}
COUNT=${2:-10}
TIMEOUT=${3:-120}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SINGLE="$SCRIPT_DIR/ocr_single.py"   # single-PDF worker, prints JSON result to stdout
OUT_DIR=${OCR_OUTPUT_DIR:-~/ocr_output}
mkdir -p "$OUT_DIR"

for i in $(seq "$START" $((START + COUNT - 1))); do
    python3 "$SINGLE" "$i" > "$OUT_DIR/result_$i.json" 2>"$OUT_DIR/err_$i.txt" &
    CPID=$!
    elapsed=0
    while kill -0 "$CPID" 2>/dev/null; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [ "$elapsed" -ge "$TIMEOUT" ]; then
            kill -9 "$CPID" 2>/dev/null
            wait "$CPID" 2>/dev/null
            echo "  ⚠ [$((i+1))] timeout after ${TIMEOUT}s — killed (SIGKILL)"
            break
        fi
    done
    if ! kill -0 "$CPID" 2>/dev/null; then
        wait "$CPID" 2>/dev/null
        echo "  ✓ [$((i+1))] done in ${elapsed}s"
    fi
done
echo "Batch complete: $COUNT items from #$START"

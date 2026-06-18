#!/usr/bin/env bash
# scripts/log-density-detector.sh — L7.F.7 (RAID cycle 33)
#
# Belt-and-suspenders detector: scans a sample log file (or stdin) and
# drops / flags lines whose PII density exceeds configured threshold.
#
# This is a complementary defense to the Vector ingest scrubber:
#   - Vector scrubber: applied per-line REPLACE in-stream.
#   - This detector:  applied as periodic OFFLINE audit; emits a metric
#                     `lw_log_density_threshold_hits_total` and flags
#                     suspicious volumes for SRE review.
#
# Cycle 33 wiring: scheduled cron in docker-compose.observability.yml
# runs this script every 5m against the last 5m of Loki output.
# Foundation V1 emits to stdout (metric written via textfile collector
# pattern); production wires to node_exporter textfile.
#
# Usage:
#   log-density-detector.sh [file]    # process file
#   cat lines | log-density-detector.sh -   # process stdin
#
# Exit codes:
#   0 — under threshold (PII density acceptable, or no PII detected)
#   1 — over threshold (SRE alert)
#   2 — usage error

set -euo pipefail

FILE="${1:-/var/log/lw/last-5m.log}"
THRESHOLD_PII_PER_KLINE="${LW_LOG_DENSITY_THRESHOLD:-5}"
PATTERNS_FILE="${LW_SCRUBBER_PATTERNS:-infra/vector/scrubber_patterns.yaml}"

if [ "$FILE" = "-" ]; then
    src=$(cat)
elif [ ! -f "$FILE" ]; then
    echo "log-density-detector: $FILE not found" >&2
    exit 2
else
    src=$(cat "$FILE")
fi

line_count=$(printf '%s' "$src" | wc -l | tr -d ' ')
if [ "$line_count" -eq 0 ]; then
    echo "lw_log_density_threshold_hits_total{result=\"empty\"} 0"
    exit 0
fi

# Count matches against the LOCKED cycle-33 pattern set
email_hits=$(printf '%s' "$src" | grep -cE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' || true)
phone_hits=$(printf '%s' "$src" | grep -cE '\+?[0-9]{1,3}[-. ]?\(?[0-9]{1,4}\)?[-. ]?[0-9]{1,4}[-. ]?[0-9]{1,9}' || true)
ipv4_hits=$(printf '%s' "$src" | grep -cE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' || true)
ssn_hits=$(printf '%s' "$src" | grep -cE '\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b' || true)
cc_hits=$(printf '%s' "$src" | grep -cE '\b[0-9]{13,19}\b' || true)

total_hits=$(( email_hits + phone_hits + ipv4_hits + ssn_hits + cc_hits ))
# Density per 1000 lines (avoid bash float; use integer math)
density_per_kline=$(( total_hits * 1000 / line_count ))

echo "[log-density-detector] line_count=${line_count} pii_hits=${total_hits} density_per_kline=${density_per_kline} threshold=${THRESHOLD_PII_PER_KLINE}"
echo "lw_log_density_lines_scanned_total ${line_count}"
echo "lw_log_density_pii_hits_total{pattern=\"email\"} ${email_hits}"
echo "lw_log_density_pii_hits_total{pattern=\"phone\"} ${phone_hits}"
echo "lw_log_density_pii_hits_total{pattern=\"ipv4\"} ${ipv4_hits}"
echo "lw_log_density_pii_hits_total{pattern=\"ssn\"} ${ssn_hits}"
echo "lw_log_density_pii_hits_total{pattern=\"cc_pan\"} ${cc_hits}"
echo "lw_log_density_per_kline ${density_per_kline}"

if [ "$density_per_kline" -gt "$THRESHOLD_PII_PER_KLINE" ]; then
    echo "lw_log_density_threshold_hits_total{result=\"over\"} 1"
    echo "[log-density-detector] ALERT: density ${density_per_kline}/kline exceeds threshold ${THRESHOLD_PII_PER_KLINE}" >&2
    exit 1
else
    echo "lw_log_density_threshold_hits_total{result=\"under\"} 0"
fi

exit 0

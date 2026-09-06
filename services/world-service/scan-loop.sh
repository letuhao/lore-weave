#!/bin/sh
# The thing that actually invokes orphan_scanner (W5-CRON).
#
# A sleep loop rather than cron: the image has no cron daemon, one process per
# container is the compose idiom, and `docker logs` then shows the scan output
# directly instead of it disappearing into a crond mailbox.
#
# EXIT CODES ARE NOT ERRORS HERE. The scanner returns 1 when it FINDS orphans —
# that is a successful scan reporting a dirty shard, and the loop must keep
# going. Only 2 (could not scan: bad config, unreachable database) means the
# scan did not happen. The two are deliberately distinct in the binary for
# exactly this reason, and collapsing them here would throw that away.
#
# The loop does NOT exit on 2 either: a database that is briefly unreachable is
# the normal state of a stack coming up, and a reaper that dies on the first
# failed connect is a reaper that is not running when it matters. It says so
# loudly and tries again.

set -u

INTERVAL="${ORPHAN_SCAN_INTERVAL_SECONDS:-3600}"

echo "[scan-loop] starting; interval=${INTERVAL}s shard=${ORPHAN_SHARD_HOST:-pg-shard-0.internal}"

while true; do
    /app/orphan_scanner --record
    code=$?
    case "$code" in
        0) : ;;  # clean
        1) echo "[scan-loop] orphans found and recorded; see orphan_scan_finding" ;;
        2) echo "[scan-loop] SCAN DID NOT RUN (config or connection). Retrying in ${INTERVAL}s." ;;
        *) echo "[scan-loop] unexpected exit ${code} from orphan_scanner" ;;
    esac
    sleep "$INTERVAL"
done

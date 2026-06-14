#!/usr/bin/env bash
# scripts/perf/w2-disk-read.sh
#
# W2.3b — dataset>RAM disk READ-thrash, LIVE (closes D-S14-DISK-READ-THRASH).
#
# Complements S14 D1 (write-fsync bound). Under a cgroup memory cap, fio random-
# reads a dataset LARGER than the cap → the page cache cannot hold it → reads hit
# the disk (cache-miss thrash). Bite: a dataset SMALLER than the cap fits in the
# page cache → reads are cache hits (much higher IOPS) → the contrast proves the
# page-cache eviction is the measured bound.
#
# LINUX-ONLY: needs a real memory cgroup to constrain the page cache. WSL2/Windows
# cannot reliably cap the page cache (the S14 finding) → NOTRUN there; the nightly
# Linux runner is where this executes. Uses a throwaway --memory-capped alpine+fio
# container (only the docker host is required, not the scale rig).
#
# Verdict: NOTRUN(2) non-Linux / no docker; FAIL(1) the big-dataset reads were NOT
# slower than the cached small-dataset (cache not the bound / vacuous); PASS(0).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
MEM="${W2_DISK_MEM:-256m}"          # cgroup memory cap
BIG="${W2_DISK_BIG:-1024}"          # MB — dataset > cap → thrash
SMALL="${W2_DISK_SMALL:-64}"        # MB — dataset < cap → cached
IMG="alpine:3.20"

log()    { printf '[w2-disk-read] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

linux_ok() { [ "$(uname -s 2>/dev/null)" = "Linux" ]; }

# Run fio random-read of a <sizeMB> file inside a --memory=<MEM> container; print IOPS.
fio_iops() { # sizeMB
  local size="$1"
  docker run --rm --memory="$MEM" --memory-swap="$MEM" "$IMG" sh -c "
    set -e
    apk add --no-cache fio >/dev/null 2>&1
    cd /tmp
    fio --name=prep --rw=write --bs=1m --size=${size}m --filename=ds --end_fsync=1 >/dev/null 2>&1
    # Random-read the dataset; with --memory=${MEM} a >cap file can't be cached.
    fio --name=randread --rw=randread --bs=4k --size=${size}m --filename=ds \
        --runtime=8 --time_based --direct=0 --minimal 2>/dev/null | awk -F';' '{print \$8}'
  "
}

main() {
  if ! linux_ok; then
    notrun "needs Linux + a real memory cgroup to constrain the page cache (this host is $(uname -s 2>/dev/null || echo non-Linux)); the nightly Linux runner executes it"
  fi
  command -v docker >/dev/null 2>&1 || notrun "docker not available"

  log "small dataset (${SMALL}MB < ${MEM} cap) — should be page-cache-served ..."
  local small_iops; small_iops="$(fio_iops "$SMALL" | tail -1)"
  log "big dataset (${BIG}MB > ${MEM} cap) — should thrash the disk ..."
  local big_iops; big_iops="$(fio_iops "$BIG" | tail -1)"
  [ -n "$small_iops" ] && [ -n "$big_iops" ] || notrun "fio produced no IOPS (image/fio unavailable?)"

  log "read IOPS: small(cached)=${small_iops} big(thrash)=${big_iops}"
  # The thrash bound: the >cap dataset must read SUBSTANTIALLY slower than the
  # cached one. Require big < small/2 (cache eviction is the real bound).
  awk -v s="$small_iops" -v b="$big_iops" 'BEGIN{exit !(b < s/2)}' \
    || fail "big-dataset IOPS (${big_iops}) NOT < half the cached small-dataset IOPS (${small_iops}) — the page cache was not the bound (cap not enforced / vacuous)"
  log "PASS: dataset>RAM random-read thrashes (IOPS ${big_iops} << cached ${small_iops}) — page-cache eviction is the read bound"
}
main "$@"

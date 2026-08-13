#!/bin/bash
# RUNBOOK entry pre-flight: SOURCE vs IMAGE by CONTENT, not by tag.
#
# PART 1 (Python): per-file md5 (CRLF-normalised) of every *.py under services/<svc>/app
#                  against /app/app in the running container.
# PART 2 (Go):     grep the RUNNING BINARY for a string literal that exists in HEAD's source.
#
# 🔴 PART 2 EXISTS BECAUSE PART 1 SILENTLY SKIPPED EVERY COMPILED SERVICE. On 2026-08-13 the
# script printed "glossary-service SKIP (no services/glossary-service/app)" and I read that as
# benign — it is Go, there is no app/ dir. The glossary binary in the running container was then
# measured to PREDATE commit 02beee08c: `already_trashed` and `glossary_user_restore` were in it,
# `KEEPS ITS CODE reserved` and `CANNOT re-add the same code` were not. A SKIP that always prints
# is indistinguishable from a pass, which is how a stale image survived a gate built to catch
# exactly that.
#
# Each probe asserts the literal is present IN SOURCE first. That is what stops the table rotting:
# when someone edits the sentence, the probe fails LOUDLY as "update the probe" rather than
# quietly passing on a literal nothing emits any more.
cd "$(git rev-parse --show-toplevel)" || exit 1

pyservices="chat-service composition-service knowledge-service glossary-service translation-service composition-worker knowledge-worker translation-worker worker-ai worker-infra"

declare -A CN=(
  [chat-service]=infra-chat-service-1
  [composition-service]=infra-composition-service-1
  [knowledge-service]=infra-knowledge-service-1
  [glossary-service]=infra-glossary-service-1
  [translation-service]=infra-translation-service-1
  [composition-worker]=infra-composition-worker-1
  [knowledge-worker]=infra-knowledge-worker-1
  [translation-worker]=infra-translation-worker-1
  [worker-ai]=infra-worker-ai-1
  [worker-infra]=infra-worker-infra-1
)
declare -A SD=(
  [chat-service]=services/chat-service
  [composition-service]=services/composition-service
  [knowledge-service]=services/knowledge-service
  [glossary-service]=services/glossary-service
  [translation-service]=services/translation-service
  [composition-worker]=services/composition-service
  [knowledge-worker]=services/knowledge-service
  [translation-worker]=services/translation-service
  [worker-ai]=services/worker-ai
  [worker-infra]=services/worker-infra
)

fail=0
echo "--- PART 1: Python services (per-file md5) ---"
for s in $pyservices; do
  c=${CN[$s]}; d=${SD[$s]}
  if ! docker ps --format '{{.Names}}' | grep -qx "$c"; then echo "$s SKIP (no container $c)"; continue; fi
  if [ ! -d "$d/app" ]; then echo "$s not-python (covered in PART 2 if compiled)"; continue; fi
  (cd "$d/app" && find . -name '*.py' | sort | while read -r f; do echo "$(tr -d '\r' < "$f" | md5sum | cut -d' ' -f1)  $f"; done) > /tmp/pf_src.md5
  docker exec "$c" sh -c "cd /app/app 2>/dev/null && find . -name '*.py' | sort | while read f; do echo \"\$(tr -d '\r' < \"\$f\" | md5sum | cut -d' ' -f1)  \$f\"; done" > /tmp/pf_img.md5 2>/dev/null
  n1=$(wc -l < /tmp/pf_src.md5); n2=$(wc -l < /tmp/pf_img.md5); dl=$(diff /tmp/pf_src.md5 /tmp/pf_img.md5 | wc -l)
  status=OK; [ "$dl" -ne 0 ] && { status="STALE"; fail=1; }
  echo "$s src=$n1 img=$n2 difflines=$dl $status"
done

echo "--- PART 2: compiled services (binary literal from HEAD) ---"
# svc|container|binary|source-glob-root|literal-introduced-by-the-service's-most-recent-commit
probes=(
  "glossary-service|infra-glossary-service-1|/glossary-service|services/glossary-service|KEEPS ITS CODE reserved"
  "book-service|infra-book-service-1|/book-service|services/book-service|FROM worlds old"
  "catalog-service|infra-catalog-service-1|/catalog-service|services/catalog-service|titleMatchesQuery"
  "agent-registry-service|infra-agent-registry-service-1|/agent-registry-service|services/agent-registry-service|surfaces where this workflow is advertised"
  "provider-registry-service|infra-provider-registry-service-1|/provider-registry-service|services/provider-registry-service|the provider reported a failure without saying why"
)
for row in "${probes[@]}"; do
  IFS='|' read -r s c bin root lit <<< "$row"
  if ! docker ps --format '{{.Names}}' | grep -qx "$c"; then echo "$s SKIP (no container $c)"; fail=1; continue; fi
  insrc=$(grep -rF -l "$lit" "$root" --include=*.go 2>/dev/null | head -1)
  if [ -z "$insrc" ]; then
    echo "$s PROBE-ROTTED (literal absent from HEAD source — update the probe, do NOT ignore)"; fail=1; continue
  fi
  n=$(docker exec "$c" sh -c "grep -a -c \"$lit\" $bin" 2>/dev/null)
  n=${n:-0}
  if [ "$n" -ge 1 ]; then echo "$s literal=present OK"; else echo "$s literal=ABSENT STALE"; fail=1; fi
done
echo "PREFLIGHT_FAIL=$fail"

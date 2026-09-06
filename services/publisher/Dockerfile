# publisher — the hop that moves a committed event onto the wire.
#
# WHY THIS EXISTS
# ---------------
# `G1`. `pkg/redisemit` is what `XADD`s to `lw.events.<reality_id>` — the exact
# stream `ChannelRoom.streamFor()` consumes — and until now the publisher had no
# Dockerfile and appeared in no compose file. So an event could be committed to
# a reality's `events` table and reach nothing: the room subscribed to a stream
# with no writer, and a browser rendered an empty roster with no error anywhere.
#
# `Dockerfile.bridge` records the same defect one service over: *"until
# 2026-08-08 it had no Dockerfile and was in no compose file — which is one of
# the reasons zero realities have ever existed."* Same shape, same consequence:
# a service that exists in the repo and in no runtime is a service nobody can
# tell is missing.
#
# CONFIG IS FAIL-CLOSED AND NAMES EVERY MISSING KEY AT ONCE
# ---------------------------------------------------------
# `loadConfig` collects the whole missing set before returning, so a half-filled
# environment reports all of it rather than one key per restart. Required:
#   PUBLISHER_ID, SHARD_HOST, META_DB_URL, REDIS_URL,
#   SHARD_DB_USER, SHARD_DB_PASSWORD
# Optional, with defaults that matter:
#   SHARD_DB_SSLMODE  (default `require` — a dev Postgres needs `disable`)
#   SHARD_DB_PORT     (5432)
#   PUBLISHER_SHARD_HOST_OVERRIDE
#   POLL_INTERVAL (1s) · HEARTBEAT_INTERVAL (10s) · BATCH_SIZE (100)
#   STREAM_MAXLEN (0 = unbounded) · PUBLISHER_HTTP_ADDR (:8080)
#
# `PUBLISHER_SHARD_HOST_OVERRIDE` deserves its own note, because it is the same
# trap `E5` fell into from the other side: `reality_registry.db_host` is a
# LOGICAL shard name pinned by a CHECK to `pg-shard-N.internal`, so a publisher
# that dialled it verbatim would resolve nothing. The override is how a real
# address is supplied without putting one in a column that forbids it.
#
# Repo-root build context, like every other Go service here — go.mod `replace`
# points at ../../contracts/{events,lifecycle,realityreg} and those must resolve
# inside the container:
#   docker build -f services/publisher/Dockerfile -t loreweave/publisher .

FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Exactly the three `replace` targets in services/publisher/go.mod, no more.
# Copying the whole repo would work and would rebuild this image whenever any
# unrelated service changed.
COPY contracts/events     /src/contracts/events
COPY contracts/lifecycle  /src/contracts/lifecycle
COPY contracts/realityreg /src/contracts/realityreg
COPY services/publisher   /src/services/publisher

WORKDIR /src/services/publisher
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/publisher ./cmd/publisher

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget

COPY --from=build /out/publisher /publisher

ENV PUBLISHER_HTTP_ADDR=:8080
EXPOSE 8080

USER nobody
# The process is fail-closed on config, so one that is UP has already parsed
# every required key and opened meta and Redis. `wget` first because the HTTP
# surface is the real signal; `nc` as the fallback for the same reason the
# bridge keeps one — a probe that can only succeed one way fails on a version
# bump to the endpoint rather than on the thing it watches.
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- --timeout=2 http://127.0.0.1:8080/healthz 2>/dev/null || \
      nc -z 127.0.0.1 8080 || exit 1
CMD ["/publisher"]

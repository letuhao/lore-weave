FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Phase 6c — repo-root build context so the go.mod `replace
# github.com/loreweave/observability => ../../sdks/go/observability`
# directive resolves inside the container. The compose file sets
# context: .. and dockerfile: services/glossary-service/Dockerfile.
# Copy the shared modules first (separate cache layer), then service files.
# grantclient (E0-1) is the shared (user,book) grant SDK; its `replace` in
# go.mod (=> ../../sdks/go/grantclient) must resolve inside the container.
COPY sdks/go/observability /src/sdks/go/observability
COPY sdks/go/grantclient /src/sdks/go/grantclient
# Plan/Action kit + LLM-gateway SDK — their go.mod replaces
# (=> ../../sdks/go/loreweave_mcp, ../../sdks/go/loreweave_llm) must resolve
# inside the container, so copy the modules into the build context.
COPY sdks/go/loreweave_mcp /src/sdks/go/loreweave_mcp
COPY sdks/go/loreweave_llm /src/sdks/go/loreweave_llm
# loreweave_extraction (D-GLOSSARY-ST-DEDUP) — shared multi-language entity-name
# normalizer; its replace (=> ../../sdks/go/loreweave_extraction) must resolve in
# the container. The data/ TSV it generates from is vendored into the module, so
# no extra context is needed beyond the module dir.
COPY sdks/go/loreweave_extraction /src/sdks/go/loreweave_extraction
# contracts/adminjwt (D-GKA-SYSTEM-TIER-ADMIN) — verifies admin RS256 JWTs; its
# replace (=> ../../contracts/adminjwt) must resolve inside the container.
COPY contracts/adminjwt /src/contracts/adminjwt
# contracts/platformjwt — shared HS256 platform-user JWT verifier; its replace
# (=> ../../contracts/platformjwt) must resolve inside the container.
COPY contracts/platformjwt /src/contracts/platformjwt
COPY services/glossary-service /src/services/glossary-service

WORKDIR /src/services/glossary-service
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/glossary-service ./cmd/glossary-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/glossary-service /glossary-service
ENV HTTP_ADDR=:8088
EXPOSE 8088
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8088/health || exit 1
CMD ["/glossary-service"]

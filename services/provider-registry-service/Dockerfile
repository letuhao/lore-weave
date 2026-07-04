FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Phase 6c — repo-root build context so the go.mod `replace
# github.com/loreweave/observability => ../../sdks/go/observability`
# directive resolves inside the container. The compose file sets
# context: .. and dockerfile: services/provider-registry-service/Dockerfile.
# Copy the shared module first (separate cache layer), then service files.
COPY sdks/go/observability /src/sdks/go/observability
# S-SETTINGS (MCP fan-out) — the settings MCP server depends on the shared Go MCP
# kit, which itself replaces github.com/loreweave/grantclient. Both must be in the
# build context for the go.mod replace directives to resolve in-container.
COPY sdks/go/loreweave_mcp /src/sdks/go/loreweave_mcp
COPY sdks/go/grantclient /src/sdks/go/grantclient
# contracts/{platformjwt,adminjwt} — shared HS256 user-JWT verifier + RS256 admin-JWT
# verifier (D-JWT-ROLE-GATE); their replace directives must resolve inside the container.
COPY contracts/platformjwt /src/contracts/platformjwt
COPY contracts/adminjwt /src/contracts/adminjwt
COPY services/provider-registry-service /src/services/provider-registry-service

WORKDIR /src/services/provider-registry-service
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/provider-registry-service ./cmd/provider-registry-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/provider-registry-service /provider-registry-service
ENV HTTP_ADDR=:8085
EXPOSE 8085
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8085/health || exit 1
CMD ["/provider-registry-service"]

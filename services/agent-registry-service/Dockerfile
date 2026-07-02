FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Repo-root build context so the go.mod `replace
# github.com/loreweave/observability => ../../sdks/go/observability` directive
# resolves in-container. Compose sets context: .. and dockerfile:
# services/agent-registry-service/Dockerfile.
COPY sdks/go/observability /src/sdks/go/observability
COPY services/agent-registry-service /src/services/agent-registry-service

WORKDIR /src/services/agent-registry-service
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/agent-registry-service ./cmd/agent-registry-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/agent-registry-service /agent-registry-service
ENV HTTP_ADDR=:8099
EXPOSE 8099
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8099/health || exit 1
CMD ["/agent-registry-service"]

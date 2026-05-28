FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Phase 6c — repo-root build context so the go.mod `replace
# github.com/loreweave/observability => ../../sdks/go/observability`
# directive resolves inside the container. The compose file sets
# context: .. and dockerfile: services/glossary-service/Dockerfile.
# Copy the shared module first (separate cache layer), then service files.
COPY sdks/go/observability /src/sdks/go/observability
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

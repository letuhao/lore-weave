FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Phase 6c — repo-root build context so the go.mod `replace
# github.com/loreweave/observability => ../../sdks/go/observability`
# directive resolves inside the container. The compose file sets
# context: .. and dockerfile: services/notification-service/Dockerfile.
# Copy the shared module first (separate cache layer), then service files.
COPY sdks/go/observability /src/sdks/go/observability
COPY services/notification-service /src/services/notification-service

WORKDIR /src/services/notification-service
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/notification-service ./cmd/notification-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/notification-service /notification-service
ENV HTTP_ADDR=:8091
EXPOSE 8091
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8091/health || exit 1
CMD ["/notification-service"]

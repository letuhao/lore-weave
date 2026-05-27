FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Phase 6c — repo-root build context so the go.mod `replace
# github.com/loreweave/observability => ../../sdks/go/observability`
# directive resolves inside the container. The compose file sets
# context: .. and dockerfile: services/usage-billing-service/Dockerfile.
# Copy the shared module first (separate cache layer), then service files.
COPY sdks/go/observability /src/sdks/go/observability
COPY services/usage-billing-service /src/services/usage-billing-service

WORKDIR /src/services/usage-billing-service
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/usage-billing-service ./cmd/usage-billing-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/usage-billing-service /usage-billing-service
ENV HTTP_ADDR=:8086
EXPOSE 8086
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8086/health || exit 1
CMD ["/usage-billing-service"]

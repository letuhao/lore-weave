FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Phase 6c — repo-root build context so the go.mod `replace
# github.com/loreweave/observability => ../../sdks/go/observability`
# directive resolves inside the container. The compose file sets
# context: .. and dockerfile: services/sharing-service/Dockerfile.
# Copy the shared module first (separate cache layer), then service files.
COPY sdks/go/observability /src/sdks/go/observability
# contracts/platformjwt — shared HS256 platform-user JWT verifier; its replace
# (=> ../../contracts/platformjwt) must resolve inside the container.
COPY contracts/platformjwt /src/contracts/platformjwt
COPY services/sharing-service /src/services/sharing-service

WORKDIR /src/services/sharing-service
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/sharing-service ./cmd/sharing-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/sharing-service /sharing-service
ENV HTTP_ADDR=:8083
EXPOSE 8083
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8083/health || exit 1
CMD ["/sharing-service"]

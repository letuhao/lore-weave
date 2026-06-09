FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Phase 6c — repo-root build context so the go.mod `replace
# github.com/loreweave/observability => ../../sdks/go/observability`
# directive resolves inside the container. The compose file sets
# context: .. and dockerfile: services/auth-service/Dockerfile.
# Copy the shared module first (separate cache layer), then service files.
COPY sdks/go/observability /src/sdks/go/observability
COPY sdks/go/serviceacl /src/sdks/go/serviceacl
COPY services/auth-service /src/services/auth-service

WORKDIR /src/services/auth-service
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/auth-service ./cmd/auth-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/auth-service /auth-service
COPY contracts/service_acl /contracts/service_acl
ENV HTTP_ADDR=:8081
ENV SERVICE_ACL_MATRIX_PATH=/contracts/service_acl/matrix.yaml
EXPOSE 8081
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8081/health || exit 1
CMD ["/auth-service"]

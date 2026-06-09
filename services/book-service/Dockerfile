FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Phase 5e-β.1 — repo-root build context so the go.mod `replace
# github.com/loreweave/llmgw => ../../sdks/go/llmgw` directive resolves
# inside the container. The compose file sets context: .. and
# dockerfile: services/book-service/Dockerfile.
#
# Phase 6c — also COPY sdks/go/observability for the second replace
# directive (github.com/loreweave/observability).
#
# Copy SDKs first (separate cache layers), then service files.
COPY sdks/go/llmgw /src/sdks/go/llmgw
COPY sdks/go/observability /src/sdks/go/observability
COPY sdks/go/serviceacl /src/sdks/go/serviceacl
COPY services/book-service /src/services/book-service

WORKDIR /src/services/book-service
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/book-service ./cmd/book-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/book-service /book-service
COPY contracts/service_acl /contracts/service_acl
ENV HTTP_ADDR=:8082
ENV SERVICE_ACL_MATRIX_PATH=/contracts/service_acl/matrix.yaml
EXPOSE 8082
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8082/health || exit 1
CMD ["/book-service"]

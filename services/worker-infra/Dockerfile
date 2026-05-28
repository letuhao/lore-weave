FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git

# Phase 6c — repo-root build context so the go.mod `replace
# github.com/loreweave/observability => ../../sdks/go/observability`
# directive resolves inside the container. The compose file sets
# context: .. and dockerfile: services/worker-infra/Dockerfile.
COPY sdks/go/observability /src/sdks/go/observability
COPY services/worker-infra /src/services/worker-infra

WORKDIR /src/services/worker-infra
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/worker-infra ./cmd/worker-infra

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /out/worker-infra /worker-infra
USER nobody
CMD ["/worker-infra"]

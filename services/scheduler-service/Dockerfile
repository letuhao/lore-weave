FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
# scheduler-service has no local `replace` deps (pgx + uuid only), so a service-only context builds.
# The compose file sets context: .. and dockerfile: services/scheduler-service/Dockerfile for repo
# consistency; copy just the service tree.
COPY services/scheduler-service /src/services/scheduler-service
WORKDIR /src/services/scheduler-service
RUN go mod download
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/scheduler-service ./cmd/scheduler-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/scheduler-service /scheduler-service
ENV HTTP_ADDR=:8095
EXPOSE 8095
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8095/health || exit 1
CMD ["/scheduler-service"]

FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
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

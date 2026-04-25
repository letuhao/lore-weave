FROM golang:1.23-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/provider-registry-service ./cmd/provider-registry-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/provider-registry-service /provider-registry-service
ENV HTTP_ADDR=:8085
EXPOSE 8085
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8085/health || exit 1
CMD ["/provider-registry-service"]

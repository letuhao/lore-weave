FROM golang:1.22-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/auth-service ./cmd/auth-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/auth-service /auth-service
ENV HTTP_ADDR=:8081
EXPOSE 8081
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8081/health || exit 1
CMD ["/auth-service"]

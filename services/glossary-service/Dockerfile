FROM golang:1.22-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/glossary-service ./cmd/glossary-service

FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/glossary-service /glossary-service
ENV HTTP_ADDR=:8088
EXPOSE 8088
USER nobody
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8088/health || exit 1
CMD ["/glossary-service"]

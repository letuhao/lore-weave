FROM golang:1.25-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/worker-infra ./cmd/worker-infra

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /out/worker-infra /worker-infra
USER nobody
CMD ["/worker-infra"]

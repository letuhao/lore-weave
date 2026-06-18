# alert-recorder — Q-L7-1 SEPARATE service (RAID cycle 34)

FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
# Pre-fetch contracts/alerts via replace directive
COPY ../../contracts/alerts/ /contracts/alerts/
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/alert-recorder ./cmd/alert-recorder

FROM gcr.io/distroless/static:nonroot
COPY --from=build /out/alert-recorder /alert-recorder
USER nonroot:nonroot
EXPOSE 8091
ENTRYPOINT ["/alert-recorder"]

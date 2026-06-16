# slo-budget-calculator — Q-L7-1 SEPARATE service (RAID cycle 34)
#
# Reads SLI + SLO target registries; exposes /healthz + /slo/targets.

FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/slo-budget-calculator ./cmd/slo-budget-calculator

FROM gcr.io/distroless/static:nonroot
COPY --from=build /out/slo-budget-calculator /slo-budget-calculator
COPY contracts/slo/ /etc/slo-budget-calculator/
USER nonroot:nonroot
EXPOSE 8090
ENTRYPOINT ["/slo-budget-calculator"]

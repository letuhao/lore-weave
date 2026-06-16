# canary-controller — L7.K.4 (RAID cycle 38). Q-L7K-1 GitHub Actions V1.
#
# SR05 §12AH.4 canary rollout executor + auto-abort. Reads deploy_audit +
# reality_registry.deploy_cohort; advances/aborts on cohort SLI burn.
#
# No third-party Go deps (stdlib only) → no go.sum to copy.

FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/canary-controller ./cmd/canary-controller

FROM gcr.io/distroless/static:nonroot
COPY --from=build /out/canary-controller /canary-controller
USER nonroot:nonroot
EXPOSE 8095
ENTRYPOINT ["/canary-controller"]

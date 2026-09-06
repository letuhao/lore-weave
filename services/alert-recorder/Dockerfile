# alert-recorder — Q-L7-1 SEPARATE service (RAID cycle 34)
#
# 🔴 REPO-ROOT BUILD CONTEXT, and it is not a style choice. This service's go.mod carries
# `replace github.com/loreweave/foundation/contracts/alerts => ../../contracts/alerts`, and a
# replace target OUTSIDE the build context cannot be copied at all — Docker resolves every
# COPY source relative to the context root, so `COPY ../../contracts/alerts/` did not reach
# the repo, it silently addressed a path that does not exist inside the context.
#
# Measured 2026-08-30, both ways round, because the previous version failed differently
# depending on where you stood and neither error named the cause:
#     context = repo root     -> "/go.sum": not found      (COPY go.mod go.sum ./)
#     context = service dir   -> "/contracts/alerts": not found
# This image had never been buildable. `D-NO-CI-BUILDS-ANY-SERVICE-IMAGE` recorded the class
# in 2026-08 and named glossary-service, which has since been fixed; nothing checked the
# others, so two services stayed broken while the suite stayed green.
#
# The shape below mirrors every WORKING Go service here (glossary, book, catalog…): copy the
# replace targets into /src first as their own cache layer, then the service, then build from
# the service directory so the `../..` in go.mod resolves.
# Build with:  docker build -f services/alert-recorder/Dockerfile <repo-root>

FROM golang:1.25-alpine AS build
WORKDIR /src

# The one `replace` target. It goes in before the service so a change to service code does
# not invalidate this layer.
COPY contracts/alerts /src/contracts/alerts
COPY services/alert-recorder /src/services/alert-recorder

WORKDIR /src/services/alert-recorder
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/alert-recorder ./cmd/alert-recorder

FROM gcr.io/distroless/static:nonroot
COPY --from=build /out/alert-recorder /alert-recorder
USER nonroot:nonroot
EXPOSE 8091
ENTRYPOINT ["/alert-recorder"]

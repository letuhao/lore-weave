# canary-controller — L7.K.4 (RAID cycle 38). Q-L7K-1 GitHub Actions V1.
#
# SR05 §12AH.4 canary rollout executor + auto-abort. Reads deploy_audit +
# reality_registry.deploy_cohort; advances/aborts on cohort SLI burn.
#
# 🔴 REPO-ROOT BUILD CONTEXT. The header used to read "No third-party Go deps (stdlib only)
# → no go.sum to copy", which was true about go.sum and hid the real problem: go.mod carries
# TWO `replace` directives pointing outside the service directory —
#     replace …/contracts/meta    => ../../contracts/meta
#     replace …/sdks/go/metapg    => ../../sdks/go/metapg
# — and NEITHER was ever copied. `go mod download` inside the container cannot resolve a
# replace whose target is not in the image, so this build failed on a dependency the comment
# said did not exist. Measured 2026-08-30; the image had never been buildable.
#
# `D-NO-CI-BUILDS-ANY-SERVICE-IMAGE` recorded this class in 2026-08 and named
# glossary-service, which has since been fixed. Nothing checked the rest, so two services
# stayed unbuildable while the whole suite stayed green — the deferral's own point, left
# standing for months because it was filed as out of scope rather than fixed.
#
# `dockerfile-replace-copy-gate.py` now derives this: every `replace => ../..` must have a
# matching COPY. It is static and fast, so it runs on every commit rather than waiting for an
# image-build CI that does not exist yet.
# Build with:  docker build -f services/canary-controller/Dockerfile <repo-root>

FROM golang:1.25-alpine AS build
WORKDIR /src

# Both `replace` targets, before the service so service edits do not bust this layer.
COPY contracts/meta /src/contracts/meta
COPY sdks/go/metapg /src/sdks/go/metapg
COPY services/canary-controller /src/services/canary-controller

WORKDIR /src/services/canary-controller
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/canary-controller ./cmd/canary-controller

FROM gcr.io/distroless/static:nonroot
COPY --from=build /out/canary-controller /canary-controller
USER nonroot:nonroot
EXPOSE 8095
ENTRYPOINT ["/canary-controller"]

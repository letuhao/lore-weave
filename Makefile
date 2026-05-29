# Makefile — local-dev convenience for L1.K lints.
# L1.K.17 — wires the 15 foundation lints into a single `make lint`.

LINTS := \
	meta-write-discipline-lint \
	pii-classify-lint \
	transitions-validation-lint \
	shard-allocation-validation \
	migration-idempotency-validator \
	observability-inventory-lint \
	capacity-budget-lint \
	dep-pinning-lint \
	timeout-discipline-lint \
	language-rule-lint \
	role-grant-validator \
	outbox-event-emit-lint \
	service-acl-matrix-lint \
	prompt-assembly-discipline-lint \
	meta-sensitive-read-bypass-lint

.PHONY: lint
lint:
	@set -e; \
	for l in $(LINTS); do \
		echo "=== $$l ==="; \
		bash scripts/$$l.sh; \
	done
	@echo "All 15 L1.K lints PASS"

.PHONY: lint-list
lint-list:
	@printf 'L1.K lints registered (%d):\n' "$$(echo $(LINTS) | wc -w)"
	@for l in $(LINTS); do printf '  %s\n' "$$l"; done

# Quick gate before push — common Go+Rust+lint sweep.
.PHONY: ci-local
ci-local: lint
	@echo "=== go test contracts/meta ==="
	cd contracts/meta && go test ./...
	@echo "=== go test contracts/lifecycle ==="
	cd contracts/lifecycle && go test ./...
	@echo "=== go test contracts/events ==="
	cd contracts/events && go test ./...
	@echo "=== go test tools/eventgen ==="
	cd tools/eventgen && go test ./...
	@echo "=== eventgen-validate (codegen drift) ==="
	bash scripts/eventgen-validate.sh
	@echo "=== cargo check workspace ==="
	cargo check --workspace
	@echo "All local CI gates PASS"

# L2.G — regenerate L2.F event registry into contracts/events/generated/ for
# all four polyglot targets (Go + Rust + TS + Python). Idempotent. CI gate is
# `scripts/eventgen-validate.sh` (see ci-local target).
.PHONY: eventgen
eventgen:
	@echo "=== building eventgen ==="
	cd tools/eventgen && go build -o eventgen .
	@echo "=== running eventgen --target all ==="
	./tools/eventgen/eventgen \
	  --registry contracts/events/_registry.yaml \
	  --events-dir contracts/events \
	  --out-dir   contracts/events/generated \
	  --target    all
	@rm -f tools/eventgen/eventgen tools/eventgen/eventgen.exe
	@echo "eventgen regeneration complete"

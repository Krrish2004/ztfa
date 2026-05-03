# ZTFA — Zero-Trust Federated Aggregation for Health IoT
# One-command demo lives at `make demo`

.PHONY: help bootstrap demo test test-unit test-e2e \
        lint fmt clean infra-up infra-down infra-logs \
        circuit contracts aggregator client portal sim \
        install-deps

SHELL := /bin/bash
N_CLIENTS ?= 3

help:
	@echo "ZTFA — make targets"
	@echo "  bootstrap     One-time: keygen, ceremony, deploy contracts, compute norm stats"
	@echo "  demo          End-to-end demo: infra up + clients + 1 federated round"
	@echo "  test          Run all tests (unit + integration)"
	@echo "  test-unit     Run unit tests across all components"
	@echo "  test-e2e      Run E2E happy-path test"
	@echo "  lint          Run all linters"
	@echo "  fmt           Format all code"
	@echo "  infra-up      Bring up postgres + minio + mosquitto + anvil"
	@echo "  infra-down    Tear down infra (volumes preserved)"
	@echo "  clean         Tear down + drop all volumes + clean build artifacts"
	@echo ""
	@echo "  N_CLIENTS=$(N_CLIENTS)  (override: make demo N_CLIENTS=5)"

# --- Infra ---
infra-up:
	docker compose up -d postgres minio minio-init mosquitto anvil
	@echo "Waiting for services to be healthy..."
	@sleep 3
	@docker compose ps

infra-down:
	docker compose down

infra-logs:
	docker compose logs -f --tail=100

clean:
	docker compose down -v
	rm -rf circuits/build/* circuits/*.r1cs circuits/*.zkey circuits/*.wtns
	rm -rf contracts/out contracts/cache contracts/broadcast
	rm -rf client/data aggregator/data
	rm -rf portal/.next portal/node_modules
	rm -rf prover/target
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete."

# --- One-time setup ---
bootstrap: infra-up
	bash scripts/bootstrap.sh

# --- Per-component build ---
circuit:
	$(MAKE) -C circuits compile

contracts:
	cd contracts && forge build

aggregator:
	cd aggregator && pip install -e . && pytest

client:
	cd client && pip install -e . && pytest

portal:
	cd portal && pnpm install && pnpm build

sim:
	cd iot-simulator && python -m pytest

# --- Demo ---
demo: bootstrap
	bash scripts/start-demo.sh
	bash scripts/run-round.sh

# --- Tests ---
test: test-unit test-e2e

test-unit:
	cd client && pytest -q
	cd aggregator && pytest -q
	cd contracts && forge test -vv
	cd circuits && npm test
	cd prover && cargo test
	cd portal && pnpm test

test-e2e:
	bash scripts/e2e_happy_path.sh

# --- Quality ---
lint:
	cd client && ruff check . && mypy src/
	cd aggregator && ruff check . && mypy src/
	cd contracts && forge fmt --check
	cd portal && pnpm lint

fmt:
	cd client && ruff format . && ruff check --fix .
	cd aggregator && ruff format . && ruff check --fix .
	cd contracts && forge fmt
	cd portal && pnpm format

# --- Dev convenience ---
install-deps:
	@echo "Installing all language toolchains' dependencies..."
	cd client && pip install -e ".[dev]"
	cd aggregator && pip install -e ".[dev]"
	cd portal && pnpm install
	cd circuits && npm install
	cd contracts && forge install
	cd prover && cargo build

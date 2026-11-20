# mcp-connectors-scanner
#
# Development:  install, test, lint, format, check
# Container:    build, up, down, restart, rebuild, logs, ps, sweep
# Service:      service-install, service-start, service-stop, service-status, service-uninstall
#
# The container targets use plain `podman run`, not podman-compose: podman-compose 1.0.6
# cannot resolve the compose file's init-step dependency. The names mirror the
# application repository's Makefile (up, down, restart, rebuild).

.PHONY: help install test lint format check run clean \
        build up serve down restart rebuild logs ps sweep \
        service-install service-start service-stop service-status service-uninstall \
        timer-install timer-uninstall \
        wait-for-networks host-verify host-install host-uninstall

# ── Container settings (override on the command line or in the shell) ──────────
ENV_FILE   ?= .env
IMAGE      ?= localhost/mcp-connectors-scanner:latest
NAME       ?= mcpc-scanner
# Three networks, each with one job (see docs): the shared Postgres (private), the scan API
# where the server and the runner reach this container (private), and this container's own
# route out. The first two are created by the main application's compose file.
NET_DB     ?= mcpc_db
NET_SCAN   ?= mcpc_scan
NET_OUT    ?= scanner_out
CACHE_VOL  ?= mcp-connectors_mcpc_scanner_cache
ALIAS      ?= mcp-scanner
SYSTEMD_DIR := $(HOME)/.config/systemd/user

help:
	@echo "mcp-connectors-scanner"
	@echo ""
	@echo "  Development"
	@echo "  make install          Install dependencies (and dev deps)"
	@echo "  make test             Run tests"
	@echo "  make lint             Run the linter"
	@echo "  make format           Run the formatter"
	@echo "  make check            Lint + test"
	@echo "  make clean            Remove build and cache artefacts"
	@echo ""
	@echo "  Container (reads $(ENV_FILE))"
	@echo "  make build            Build the image"
	@echo "  make up               Start the scanner in the background (idempotent)"
	@echo "  make down             Stop and remove the scanner container"
	@echo "  make restart          Recreate the container from the current image"
	@echo "  make rebuild          Rebuild the image without cache, then recreate"
	@echo "  make logs             Follow the scanner log"
	@echo "  make ps               Show scanner containers"
	@echo "  make sweep            Run one full sweep now, in a separate throwaway container"
	@echo ""
	@echo "  Service (systemd user unit; keeps the scanner running)"
	@echo "  make service-install  Install and enable the service"
	@echo "  make service-start | service-stop | service-status | service-uninstall"
	@echo "  make timer-install    Enable the weekly sweep timer (Mondays) | timer-uninstall"
	@echo ""
	@echo "  Host service (system unit like the application's; starts the scanner at boot, needs sudo)"
	@echo "  make host-verify      Check the unit with systemd-analyze, install nothing"
	@echo "  make host-install     Verify, install and enable it | host-uninstall"
	@echo "                        Use this or the user service above, never both"

# ── Development ───────────────────────────────────────────────────────────────

install:
	uv sync --extra dev

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint test

# `run` starts the container in the foreground-less way the service uses.
run: up

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .ruff_cache/ .mypy_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +

# ── Container ─────────────────────────────────────────────────────────────────

build:
	@echo "Building $(IMAGE)"
	@podman build -t $(IMAGE) .

# Reads secrets from $(ENV_FILE) (gitignored). Nothing is printed.
# RUN_MODE is -d for `make up` and empty for the service, which wants the
# container in the foreground so systemd can supervise it.
RUN_MODE ?= -d
RESTART_FLAG ?= --restart unless-stopped
define RUN_SCANNER
	@test -r $(ENV_FILE) || { echo "missing $(ENV_FILE): copy .env.example and fill it in"; exit 2; }
	@set -a; . ./$(ENV_FILE); set +a; \
	podman run $(RUN_MODE) --name $(NAME) $(RESTART_FLAG) \
	  --network $(NET_DB) --network $(NET_SCAN):alias=$(ALIAS) --network $(NET_OUT) \
	  --read-only --cap-drop ALL --security-opt no-new-privileges -u 10002:10002 \
	  --tmpfs /work:size=6g,mode=1777 --tmpfs /tmp:size=512m,mode=1777 \
	  -v $(CACHE_VOL):/home/scanner \
	  -e SCAN_INTERVAL_HOURS="$${SCAN_INTERVAL_HOURS:-168}" \
	  -e SCAN_CONCURRENCY="$${SCAN_CONCURRENCY:-32}" \
	  -e SCAN_WORK_DIR=/work -e SCAN_OUT_DIR=/out \
	  -e SCAN_FEED_URL="$${SCAN_FEED_URL:-http://mcp-server:8080/internal/scanner/catalog}" \
	  -e SCAN_FEED_TOKEN="$$SCAN_FEED_TOKEN" \
	  -e SCANNER_API_TOKEN="$$SCANNER_API_TOKEN" \
	  -e SCANNER_API_ADDR=:9090 \
	  -e SCANNER_DATABASE_URL="postgres://scanner:$$SCANNER_DB_PASSWORD@$${SCANNER_PG_HOST:-mcp-db}:5432/scanner?sslmode=disable" \
	  $(IMAGE) > /dev/null
endef

up:
	@if podman container exists $(NAME); then \
	  if [ "$$(podman inspect -f '{{.State.Running}}' $(NAME))" = "true" ]; then echo "$(NAME) is already running"; \
	  else podman start $(NAME) > /dev/null && echo "$(NAME) started"; fi; \
	else echo "Starting $(NAME)"; $(MAKE) --no-print-directory _create && echo "$(NAME) created"; fi

_create:
	$(RUN_SCANNER)

# Foreground run for systemd: replaces any stale container of the same name, then
# stays attached. systemd restarts it on failure, so podman's own restart policy is
# switched off to avoid two supervisors fighting over one container.
serve:
	@podman rm -f $(NAME) > /dev/null 2>&1 || true
	@$(MAKE) --no-print-directory _create RUN_MODE= RESTART_FLAG=--restart=no

down:
	@echo "Shutting down $(NAME)"
	@podman stop -t 30 $(NAME) > /dev/null 2>&1 || true
	@podman rm -f $(NAME) > /dev/null 2>&1 || true

restart: down
	@echo "Recreating $(NAME)"
	@$(MAKE) --no-print-directory _create

rebuild:
	@echo "Rebuilding image without cache..."
	@podman build --no-cache -t $(IMAGE) .
	@$(MAKE) --no-print-directory restart

logs:
	@podman logs -f --tail 100 $(NAME)

ps:
	@podman ps -a --filter name=mcpc-scanner --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

sweep:
	@SCANNER_ENV_FILE=$(abspath $(ENV_FILE)) deploy/sweep-once.sh

# ── systemd user service ──────────────────────────────────────────────────────
# The unit runs the container in the foreground (`make serve`) so systemd supervises
# it and restarts it on failure, like the application's own service. Run `make down`
# first if the container was started by hand, so the unit can take over the name.

service-install:
	@mkdir -p $(SYSTEMD_DIR)
	@sed "s#@REPO@#$(CURDIR)#g" deploy/systemd/mcpc-scanner.service > $(SYSTEMD_DIR)/mcpc-scanner.service
	@systemctl --user daemon-reload
	@systemctl --user enable mcpc-scanner.service
	@echo "installed. Start it with: make service-start"

service-start:
	@systemctl --user start mcpc-scanner.service
	@systemctl --user --no-pager status mcpc-scanner.service | head -n 6

service-stop:
	@systemctl --user stop mcpc-scanner.service

service-status:
	@systemctl --user --no-pager status mcpc-scanner.service | head -n 12

service-uninstall:
	@systemctl --user disable --now mcpc-scanner.service 2>/dev/null || true
	@rm -f $(SYSTEMD_DIR)/mcpc-scanner.service
	@systemctl --user daemon-reload

# ── systemd system service ───────────────────────────────────────
# The same arrangement as the application's host/mcp-connectors.service: a system unit that
# starts at boot and runs as the person who owns this checkout. Use it instead of the user
# service above, never together with it, because both would run the same container.

HOST_UNIT := mcp-connectors-scanner.service

# Waits up to two minutes for the networks the application's stack creates, so the unit can be
# ordered after that stack at boot without needing it to be fully up.
wait-for-networks:
	@for i in $$(seq 1 60); do \
	  podman network exists $(NET_DB) && podman network exists $(NET_SCAN) && exit 0; sleep 2; \
	done; echo "the application's networks $(NET_DB) and $(NET_SCAN) do not exist yet" >&2; exit 1

host-verify:
	@test "$$(id -u)" != 0 || { echo "run this as your normal user, not root: the unit runs the scanner as you"; exit 2; }
	@d=$$(mktemp -d) && sed -e "s#@REPO@#$(CURDIR)#g" -e "s#@USER@#$$(id -un)#g" host/$(HOST_UNIT) > $$d/$(HOST_UNIT) \
	  && systemd-analyze verify $$d/$(HOST_UNIT) && echo "$(HOST_UNIT): the unit is valid"; rc=$$?; rm -rf $$d; exit $$rc

host-install: host-verify
	@! systemctl --user is-enabled mcpc-scanner.service > /dev/null 2>&1 || { echo "the user service is enabled; run 'make service-uninstall' first, so two units do not fight over one container"; exit 2; }
	@sed -e "s#@REPO@#$(CURDIR)#g" -e "s#@USER@#$$(id -un)#g" host/$(HOST_UNIT) | sudo tee /etc/systemd/system/$(HOST_UNIT) > /dev/null
	@sudo systemctl daemon-reload
	@sudo systemctl enable $(HOST_UNIT)
	@echo "installed and enabled. Start it with: sudo systemctl start $(HOST_UNIT)"

host-uninstall:
	@sudo systemctl disable --now $(HOST_UNIT) 2>/dev/null || true
	@sudo rm -f /etc/systemd/system/$(HOST_UNIT)
	@sudo systemctl daemon-reload

timer-install:
	@mkdir -p $(SYSTEMD_DIR)
	@sed "s#@REPO@#$(CURDIR)#g" deploy/systemd/mcpc-scanner-sweep.service > $(SYSTEMD_DIR)/mcpc-scanner-sweep.service
	@cp deploy/systemd/mcpc-scanner-sweep.timer $(SYSTEMD_DIR)/
	@systemctl --user daemon-reload
	@systemctl --user enable --now mcpc-scanner-sweep.timer
	@systemctl --user list-timers mcpc-scanner-sweep.timer --no-pager | head -n 3

timer-uninstall:
	@systemctl --user disable --now mcpc-scanner-sweep.timer 2>/dev/null || true
	@rm -f $(SYSTEMD_DIR)/mcpc-scanner-sweep.service $(SYSTEMD_DIR)/mcpc-scanner-sweep.timer
	@systemctl --user daemon-reload

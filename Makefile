# Illuminate — day-to-day targets. `make help` lists them.
.DEFAULT_GOAL := help
COMPOSE ?= docker compose
BACKUP  ?=
NAME    ?=
export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)

.PHONY: help up down dev seed backup restore backups sync-pre sync-publish test-sync-main

help:
	@echo "make up                 start everything in containers (web :8080, api :8000, neo4j :7474)"
	@echo "make down               stop containers (data volumes are kept)"
	@echo "make dev                neo4j in docker, api + web on the host with hot reload"
	@echo "make seed               rebuild the demo graph from committed fixtures (offline)"
	@echo "make backup [NAME=x]    stop neo4j, archive neo4j volume + api/data to backups/, restart neo4j"
	@echo "make restore BACKUP=x   replace neo4j volume + api/data from backups/x (or BACKUP=latest)"
	@echo "make backups            list archives in backups/"
	@echo "make sync-pre           fetch and safely fast-forward canonical main; never push"
	@echo "make sync-publish       fetch, reconcile, and publish reviewed canonical main"
	@echo "make test-sync-main     test synchronization using disposable local repositories"

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

dev:
	scripts/dev.sh

seed:
	scripts/seed.sh --offline

# Neo4j must be stopped for a consistent copy of its store; restarted afterwards if it was up.
backup:
	@mkdir -p backups api/data
	@was_up=$$($(COMPOSE) ps -q --status running neo4j); \
	[ -z "$$was_up" ] || $(COMPOSE) stop neo4j; \
	NAME="$(NAME)" $(COMPOSE) run --rm --no-deps backup; rc=$$?; \
	[ -z "$$was_up" ] || $(COMPOSE) start neo4j; \
	exit $$rc

# Stops neo4j and api (if running), restores, then starts neo4j again so it picks up the new store.
restore:
	@test -n "$(BACKUP)" || { echo "usage: make restore BACKUP=<file in backups/ | latest>"; exit 2; }
	@mkdir -p backups api/data
	@was_up=$$($(COMPOSE) ps -q --status running neo4j); \
	$(COMPOSE) stop api neo4j 2>/dev/null; \
	BACKUP="$(BACKUP)" $(COMPOSE) run --rm --no-deps restore; rc=$$?; \
	[ $$rc -ne 0 ] || [ -z "$$was_up" ] || $(COMPOSE) start neo4j; \
	exit $$rc

backups:
	@ls -lh backups/*.tgz 2>/dev/null || echo "no backups yet — run make backup"
	@[ ! -f backups/.latest ] || echo "latest: $$(cat backups/.latest)"

sync-pre:
	@scripts/sync-main.sh --check

sync-publish:
	@scripts/sync-main.sh --publish

test-sync-main:
	@scripts/test-sync-main.sh

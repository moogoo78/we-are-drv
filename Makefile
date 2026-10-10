# Default targets run behind Traefik (compose.traefik.yml, needs .env DRV_HOST).
# Use the *-local targets on a machine without the Traefik network.
COMPOSE = docker compose -f docker-compose.yml -f compose.traefik.yml
LOCAL = docker compose -f docker-compose.yml

.PHONY: help build up down restart logs ps up-local down-local restart-local up-traefik down-traefik restart-traefik clean

help:
	@echo "Targets:"
	@echo "  make up              - build and start behind Traefik (needs .env DRV_HOST)"
	@echo "  make down            - stop and remove the containers"
	@echo "  make restart         - down + up"
	@echo "  make build           - build the images without starting them"
	@echo "  make logs            - follow container logs"
	@echo "  make ps              - show container status"
	@echo "  make up-local        - build and start without Traefik (localhost:8020 only)"
	@echo "  make down-local      - stop the local stack"
	@echo "  make restart-local   - down-local + up-local"
	@echo "  make clean           - down + remove the built image"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

up-local:
	$(LOCAL) up -d --build

down-local:
	$(LOCAL) down

restart-local: down-local up-local

# Kept as aliases for the old Traefik targets.
up-traefik: up
down-traefik: down
restart-traefik: restart

clean: down
	docker image rm we-are-drv 2>/dev/null || true

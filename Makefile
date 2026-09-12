COMPOSE = docker compose
TRAEFIK = -f docker-compose.yml -f compose.traefik.yml

.PHONY: help build up down restart logs ps up-traefik down-traefik restart-traefik clean

help:
	@echo "Targets:"
	@echo "  make up              - build and start the container (localhost:8020)"
	@echo "  make down            - stop and remove the container"
	@echo "  make restart         - down + up"
	@echo "  make build           - build the image without starting it"
	@echo "  make logs            - follow container logs"
	@echo "  make ps              - show container status"
	@echo "  make up-traefik      - build and start behind Traefik (needs .env DRV_HOST)"
	@echo "  make down-traefik    - stop the Traefik-fronted stack"
	@echo "  make restart-traefik - down-traefik + up-traefik"
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

up-traefik:
	$(COMPOSE) $(TRAEFIK) up -d --build

down-traefik:
	$(COMPOSE) $(TRAEFIK) down

restart-traefik: down-traefik up-traefik

clean: down
	docker image rm we-are-drv 2>/dev/null || true

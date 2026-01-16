.PHONY: up down build logs health ps clean test dashboard

# start services
up:
	docker-compose up -d --build

# stop services
down:
	docker-compose down

# build without starting
build:
	docker-compose build

# view logs (all services)
logs:
	docker-compose logs -f

# check health of all services
health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/health || echo "API Gateway: DOWN"
	@curl -s http://localhost:8001/health || echo "Search Service: DOWN"
	@curl -s http://localhost:8002/health || echo "Product Service: DOWN"
	@curl -s http://localhost:8003/health || echo "Ranking Service: DOWN"

# show running containers
ps:
	docker-compose ps

# clean up everything (including volumes)
clean:
	docker-compose down -v --rmi local

# run a test search
test:
	curl -s "http://localhost:8000/search?q=laptop"

# open grafana
dashboard:
	open http://localhost:3000

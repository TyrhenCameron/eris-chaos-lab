# ERIS

Chaos engineering platform I built to learn about distributed systems resilience. Named after the Greek goddess of chaos.

## What it does

ERIS is a microservices-based e-commerce search system with built-in chaos testing. You can inject failures (kill services, freeze them, add network delays) while traffic is flowing and watch how the system responds using visualization software. The services should demonstrate graceful failure.

## The setup

Four microservices that handle product search:
- **api-gateway** (8000) - entry point
- **search-service** (8001) - coordinates the search
- **product-service** (8002) - talks to Postgres and Redis
- **ranking-service** (8003) - scores results by relevance

The chaos tools:
- **chaos-controller** (8080) - injects failures into services
- **load-generator** (8085) - sends continuous traffic for testing
- **prometheus** (9090) - collects metrics
- **grafana** (3000) - visualizes everything

## Running it

```bash
docker-compose up -d --build
```

Test that search works:
```bash
curl "http://localhost:8000/search?q=laptop"
```

## Running chaos experiments

Start some traffic first:
```bash
curl -X POST http://localhost:8085/start
```

Then break something:
```bash
curl -X POST http://localhost:8080/experiment \
  -H "Content-Type: application/json" \
  -d '{"target_service": "api-gateway", "experiment_type": "container_pause", "duration_seconds": 30}'
```

Watch the dashboard at http://localhost:3000 (see .env) - you'll see the error rate spike when the service is paused.

## Experiment types

- `container_kill` - stops the container completely
- `container_pause` - freezes it (simulates a hang)
- `network_delay` - adds latency to requests
- `cpu_stress` - maxes out the CPU

## Built with

Python, FastAPI, Docker, PostgreSQL, Redis, Prometheus, Grafana

<p align="center">
  <img src="assets/logo.png" width="150">
</p>

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
- **experiment-runner** (8090) - automated chaos experiments with hypothesis testing
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

## Monitoring

Open Grafana to watch metrics in real-time:
- URL: http://localhost:3000
- Login: admin / (see .env)
- Dashboard: "ERIS Chaos Dashboard"

Prometheus (raw metrics): http://localhost:9090

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

## Automated experiments

The experiment-runner automates chaos using the scientific method:

1. Check steady state before chaos
2. Inject failure
3. Monitor for abort conditions (safety)
4. Validate system recovers after chaos
5. Generate pass/fail report

Run a pre-defined experiment:
```bash
curl -X POST http://localhost:8090/run/api-gateway-pause
```

Example output:
```json
{
  "status": "passed",
  "hypothesis": "System should recover to steady state within 30 seconds",
  "steady_state_before": {"error_rate": 0.0, "latency_p95": 0.048},
  "steady_state_after": {"error_rate": 0.0, "latency_p95": 0.048},
  "summary": "Hypothesis validated: system recovered to steady state after chaos"
}
```

Experiments are defined in YAML files in `services/experiment-runner/experiments/`.

## Experiment types

- `container_kill` - stops the container completely
- `container_pause` - freezes it (simulates a hang)
- `network_delay` - adds latency to requests
- `cpu_stress` - maxes out the CPU

## Built with

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=for-the-badge&logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?style=for-the-badge&logo=grafana&logoColor=white)

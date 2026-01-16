# ERIS - Chaos Engineering Platform

A chaos engineering platform for testing system resilience through controlled failure injection.

## Quick Start

```bash
# Start all services
make up

# Check health
make health

# Run a chaos experiment
./chaos/cli.py run container-kill --target search-service --duration 30s

# View metrics dashboard
open http://localhost:3000

# Stop everything
make down
```

## Technologies

- Python / FastAPI
- Docker / Docker Compose
- PostgreSQL
- Redis
- Prometheus
- Grafana

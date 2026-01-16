from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import PlainTextResponse
import httpx
import time
import os

app = FastAPI(title="ERIS API Gateway")

# tracking Prometheus Metrics through scraping. counting requests and latency percentiles
REQUEST_COUNT = Counter(
    'gateway_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status']
)
REQUEST_LATENCY = Histogram(
    'gateway_request_latency_seconds',
    'Request latency',
    ['endpoint']
)

# service urls for docker
SEARCH_SERVICE = os.getenv("SEARCH_SERVICE_URL", "http://search-service:8001")

# health check
@app.get("/health")
async def health():
    """Health check endpoint - used by Docker and load balancers"""
    return {"status": "healthy", "service": "api-gateway"}

# metrics endpoint
@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus scrapes this endpoint to collect metrics"""
    return generate_latest()

# main search endpoint
@app.get("/search")
async def search(q: str):
    """
    Main entry point for search queries.
    Forwards request to search-service and returns results.
    """
    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{SEARCH_SERVICE}/search",
                params={"q": q}
            )
            response.raise_for_status()

            # record success metrics
            REQUEST_COUNT.labels(
                method='GET',
                endpoint='/search',
                status='200'
            ).inc()

            return response.json()

    except httpx.TimeoutException:
        REQUEST_COUNT.labels(method='GET', endpoint='/search', status='timeout').inc()
        raise HTTPException(status_code=504, detail="Search service timeout")
    except httpx.HTTPError as e:
        REQUEST_COUNT.labels(method='GET', endpoint='/search', status='error').inc()
        raise HTTPException(status_code=502, detail=f"Search service error: {str(e)}")

    finally:
        # always record latency
        REQUEST_LATENCY.labels(endpoint='/search').observe(time.time() - start_time)

# root endpoint
@app.get("/")
async def root():
    return {
        "service": "ERIS API Gateway",
        "version": "1.0.0",
        "endpoints": ["/search", "/health", "/metrics"]
    }

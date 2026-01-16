from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import PlainTextResponse
import httpx
import time
import os

app = FastAPI(title="ERIS Search Service")

# prometheus metrics
REQUEST_COUNT = Counter(
    'search_requests_total',
    'Total search requests',
    ['status']
)
REQUEST_LATENCY = Histogram(
    'search_request_latency_seconds',
    'Search request latency'
)

# service urls
PRODUCT_SERVICE = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8002")
RANKING_SERVICE = os.getenv("RANKING_SERVICE_URL", "http://ranking-service:8003")

# health check
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "search-service"}

# metrics
@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return generate_latest()

# search logic
@app.get("/search")
async def search(q: str):
    """
    Flow:
    1. Call product-service to find matching products
    2. Call ranking-serivce to order results
    3. return ranked results
    """
    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 1. Get products matching the query
            product_response = await client.get(
                f"{PRODUCT_SERVICE}/products/search",
                params={"q": q}
            )
            product_response.raise_for_status()
            products = product_response.json()

            # if no product found, return empty
            if not products:
                REQUEST_COUNT.labels(status='success').inc()
                return {"query": q, "results": [], "count": 0}

            # 2. rank the products
            rank_response = await client.post(
                f"{RANKING_SERVICE}/rank",
                json={"query": q, "products": products}
            )
            rank_response.raise_for_status()
            ranked_results = rank_response.json()

            REQUEST_COUNT.labels(status='success').inc()
            return {
                "query": q,
                "results": ranked_results,
                "count" : len(ranked_results)
            }

    except httpx.TimeoutException:
        REQUEST_COUNT.labels(status='timeout').inc()
        raise HTTPException(status_code=504, detail="Downstream service timeout")

    except httpx.HTTPError as e:
        REQUEST_COUNT.labels(status='error').inc()
        raise HTTPException(status_code=502, detail=f"Downstream service error: {str(e)}")

    finally:
        REQUEST_LATENCY.observe(time.time() - start_time)

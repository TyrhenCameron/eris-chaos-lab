from fastapi import FastAPI
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import List, Any
import time

app = FastAPI(title="ERIS Ranking Service")

# prometheus metrics
REQUEST_COUNT = Counter(
    'ranking_requests_total',
    'Total ranking requests',
    ['status']
)

REQUEST_LATENCY = Histogram(
    'ranking_request_latency_seconds',
    'Ranking request latency'
)

# request model
class RankRequest(BaseModel):
    query: str
    products: List[dict]

# health check
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ranking services"}

# metrics
@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return generate_latest()

# ranking logic
@app.post("/rank")
async def rank_products(request: RankRequest):
    """
    Rank products by relevance to the search query.

    Simple scoring algorithm
    - exact name match -> 100 points
    - query word in name -> 50 points per word
    - query word in description -> 20 pointers per word
    - lower price -> 10 points
    """

    start_time = time.time()

    query_words = request.query.lower().split()
    scored_products = []

    for product in request.products:
        score = 0
        name = product.get('name', '').lower()
        description = product.get('description', '').lower()
        price = float(product.get('price', 0))

        if request.query.lower() in name:
            score += 100

        for word in query_words:
            if word in name:
                score += 50
            if word in description:
                score += 20

        if price > 0:
            score += max(0, 10 - (price / 1000))

        scored_products.append({
            **product,
            '_score': round(score, 2)
        })

    # sort by score descending
    ranked = sorted(scored_products, key=lambda x: x['_score'], reverse=True)

    REQUEST_COUNT.labels(status='success').inc()
    REQUEST_LATENCY.observe(time.time() - start_time)

    return ranked

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import PlainTextResponse
import asyncpg
import redis
import json
import os

app = FastAPI(title="ERIS Product Service")

# Prometheus Metrics
REQUEST_COUNT = Counter(
    'product_requests_total',
    'Total product requests',
    ['endpoint', 'status']
)
CACHE_HITS = Counter('product_cache_hits_total', 'Cache hits')
CACHE_MISSES = Counter('product_cache_misses_total', 'Cache misses')

# config
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://REDACTED:REDACTED@postgres:5432/products")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# DB connection pool
db_pool = None
redis_client = None

@app.on_event("startup")
async def startup():
    """Initialize connections when on service startup"""
    global db_pool, redis_client

    # connect to PostgreSQL
    db_pool = await asyncpg.create_pool(DATABASE_URL)

    # connect to Redis
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

    # create products table if not exists
    async with db_pool.acquire() as conn:
        await conn.execute('''
                        CREATE TABLE IF NOT EXISTS products (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        price DECIMAL(10,2),
                        category VARCHAR(100)
                        )
                        ''')

        count = await conn.fetchval('SELECT COUNT(*) FROM products')
        if count == 0:
            await conn.executemany('''
                                INSERT INTO products (name, description, price, category)
                                VALUES ($1, $2, $3, $4)
                                ''', [
                                    ('Laptop Pro 15', 'High-performance laptop', 1299.99, 'electronics'),
                                    ('Wireless Gaming Mouse', 'Ergonomic wireless mouse for gaming (low latency)', 89.99, 'electronics'),
                                    ('USB-C Hub', '7-in-1 USB-C adapter', 59.99, 'electronics'),
                                    ('Mechanical Keyboard', 'RGB Mechanical Keyboard', 149.99, 'electronics'),
                                    ('Final Fantasy XXIX', 'The Newest Title for Square-Enix', 89.99, 'video games'),
                                    ('The Snitcher II', 'The sequel from the critically acclaimed title from BD Projecht Blu', 79.99, 'video games'),
                                    ('RTX 9990', 'top of the line graphics board from NVIDIA', 9999.99, 'electronics'),
                                    ('ATX Computer Bag', 'Big tower? No problem. Bring your baby in peace of mind ', 129.99, 'accessories'),
                                    ('Laptop Pro 16', 'Because the Laptop Pro 15 was so last 6 months ago', 2199.99, 'electronics'),
                                    ('Webcam HD', 'shows your past if you let it', 1.99, 'electronics'),
                                ])

@app.on_event("shutdown")
async def shutdown():
    """Clean up connections when service stops"""
    global db_pool
    if db_pool:
        await db_pool.close()

# health check
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "product-service"}

# metrics
@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return generate_latest()

# search products
@app.get("/products/search")
async def search_products(q: str):
    """
    Search from products matching query.
    Uses Redis cache for frequently searched terms.
    """

    cache_key = f"search:{q.lower()}"

    # try cache first
    cached = redis_client.get(cache_key)
    if cached:
        CACHE_HITS.inc()
        REQUEST_COUNT.labels(endpoint='/products/search', status='success').inc()

        return json.loads(cached)

    CACHE_MISSES.inc()

    # query database
    async with db_pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT id, name, description, price, category
            FROM products
            WHERE name ILIKE $1 OR description ILIKE $1 OR category ILIKE $1''', f'%{q}%')
        products = [dict(row) for row in rows]

        # Cache results for 60 seconds
        redis_client.setex(cache_key, 60, json.dumps(products, default=str))
        REQUEST_COUNT.labels(endpoint='/products/search', status='success').inc()

        return products

# get product by id
@app.get("/products/{product_id}")
async def get_product(product_id: int):
    """Get a single product by ID"""
    cache_key = f"product:{product_id}"

    #Try cache first
    cached = redis_client.get(cache_key)
    if cached:
        CACHE_HITS.inc()
        return json.loads(cached)

    CACHE_MISSES.inc()

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT id, name, description, price, category FROM products WHERE id = $1',
            product_id
        )

        if not row:
            raise HTTPException(status_code=404, detail="Product not found")

        product = dict(row)
        redis_client.setex(cache_key, 300, json.dumps(product, default=str))

        return product

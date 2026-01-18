from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import httpx
import asyncio
from datetime import datetime
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi.responses import PlainTextResponse

app = FastAPI(title="ERIS Load Generator")

# metrics we wanna measure
# incremental counter
REQUESTS_SENT = Counter(
    'loadgen_requests_total',
    'Total requests sent by load generator',
    ['target', 'status'] #which service, success/fail
)

# histogram for distribution of response times (averages, 95 percentile, etc.)
RESPONSE_TIME = Histogram(
    'loadgen_response_time_seconds',
    'Response time of requests',
    ['target']
)

# gauge counts current values
CURRENT_RPS = Gauge(
    'loadgen_current_rps',
    'Current requests per second setting'
)

# define state or what we need to track
# load gen state: track whether load gen is running and store background task ref
load_test_running = False
load_test_task = None # holds asyncio task so we can cancel it

# user config definitions
class LoadConfig(BaseModel):
    target_url: str = "http://api-gateway:8000/search?q=laptop"
    requests_per_second: int = 10 #requests to send/second
    duration_seconds: Optional[int] = None #run forever until stopped

# store config
current_config = LoadConfig()

# endpoints for health and metrics
@app.get("/health")
async def health():
    return {
        "status" : "healthy",
        "service" : "load-generator",
        "load_test_running" : load_test_running
    }

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return generate_latest()

# core load gen function
# background function that sends requests
async def generate_load(config: LoadConfig):
    #mark load test as running
    global load_test_running
    load_test_running = True
    # set rps metric to current setting
    CURRENT_RPS.set(config.requests_per_second)

    # create http client
    async with httpx.AsyncClient(timeout=10.0) as client:
        start_time = datetime.now()

        # if duratoin set and we've exceeded it break
        while load_test_running:
            if config.duration_seconds:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= config.duration_seconds:
                    break

            #calculate delay
            delay = 1.0 / config.requests_per_second

            try:
                # record request start time
                req_start = datetime.now()
                # send get request to target url
                response = await client.get(config.target_url)
                # record request end time and calc duration
                req_duration = (datetime.now() - req_start).total_seconds()

                # record duration in RESPONSE_TIME histoggram
                RESPONSE_TIME.labels(target=config.target_url).observe(req_duration)

                if response.status_code == 200:
                    REQUESTS_SENT.labels(target=config.target_url, status="success").inc()
                else:
                    REQUESTS_SENT.labels(target=config.target_url, status="error").inc()

            except Exception as e:
                # request failed (timeout, connection refused, whatever)
                REQUESTS_SENT.labels(target=config.target_url, status="failed").inc()

            await asyncio.sleep(delay)

        load_test_running = False
        CURRENT_RPS.set(0)

# start load test
@app.post("/start")
async def start_load_test(config: LoadConfig = None):
    global load_test_running, load_test_task, current_config

    # dont start if already running
    if load_test_running:
        return {"status": "already running", "config": current_config}

    # use provided config or default
    if config:
        current_config = config

    # start function in background with asyncio
    load_test_task = asyncio.create_task(generate_load(current_config))

    # return started with config details
    return {
        "status": "started",
        "config": {
            "target_url": current_config.target_url,
            "requests_per_second": current_config.requests_per_second,
            "duration_seconds": current_config.duration_seconds
        }
    }

# stop load test
@app.post("/stop")
async def stop_load_test():
    global load_test_running, load_test_task

    # if not running then return so
    if not load_test_running:
        return {"status": "not running"}
    # signal loop to stop
    load_test_running = False

    #wait for task to finish cleanly
    if load_test_task:
        await load_test_task

    #then return stopped status
    return {"status": "stopped"}

# get current status
@app.get("/status")
async def get_status():
    return {
        "running": load_test_running,
        "config": {
            "target_url": current_config.target_url,
            "requests_per_second": current_config.requests_per_second,
            "duration_seconds": current_config.duration_seconds
        }
    }

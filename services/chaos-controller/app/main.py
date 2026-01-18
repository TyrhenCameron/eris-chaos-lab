from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum
import docker
import asyncio
import httpx
from datetime import datetime
fromt prometheus_client import Counter, generate_latest
from fastapi.responses import PlainTextResponse

app = FastAPI(title="ERIS Chaos Controller")

# docker remote control - can list containers, stop them, pause, them, run commands inside them
docker_client = docker.from_end()

# prometheus and grafana metrics
EXPERIMENTS_RUN = Counter(
    'chaos_experiments_total',
    'Total chaos experiments run',
    ['experiment_type', 'target', 'status']
)

# enumeration for tests
class ExperimentType(str, Enum):
    CONTAINER_KILL = "container_kill"
    CONTAINER_PAUSE = "container_pause"
    NETWORK_DELAY = "network_delay"
    CPU_STRESS = "cpu_stress"

# pydantic model (request validation) to define shape of data
class ExperimentRequest(BaseModel):
    target_service: str # which service to attack
    experiment_type: ExperimentType # what type of chaos to cause
    duration_seconds: Optional[int] = 30 # default 30 seconds -- not req --
    intensity: Optional[int] = 50 # 1-100 severity scale -- not req --

# in-memory storage: use PostgreSQL in production!!!
experiment_history: List[dict] = []

# /health endpoint for Docker healthchecks, load balancers, Kubeternetes and monitorying
@app.get("/health")
async def health():
    return {"status": "healthy", "services": "chaos-controller"}

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return generate_latest()

# list available targets
@app.get("/targets")
async def list_targets():
    containers = docker_client.containers.list()

    targets = [
        {
            "name": c.name,
            "status": c.status,
            "image": c.image.tags[0] if c.image.tags else "unknown"
        }
        for c in containers
    ]
    return {"targets": targets}

# the goodies
@app.post("/experiment")
async def run_experiment(request: ExperimentRequest):

    # find target container - fuzzy matching
    containers = docker_client.containers.list(
        filters={"name": request.target_service}
    )

    # error handling
    if not containers:
        raise HTTPException(
            status_code=404,
            detail=f"Service {request.target_service} not found"
        )

    # take first item from the list if there are multiple
    target_container = containers[0]

    #record when experiment started
    start_time = datetime.now()

    # experiment block
    try:
        # power word: kill (for containers)
        # completely stop container until manually restarted
        # service unavailable
        if request.experiment_type == ExperimentType.CONTAINER_KILL:
            target_container.stop()
            result = "Container stopped"

        # time stop
        # deadlock, infinite loop, GC pause, frozen process
        # service time out
        elif request.experiment_type == ExperimentType.CONTAINER_PAUSE:
            target_container.pause()
            await asyncio.sleep(request.duration_seconds) #regular time.sleep would freeze entire controller
            target_container.unpause()
            result = f"Container paused for {request.duration_second}s"

        # eepyblackcat.jpg
        # slow network, geographic latency, congested network sim
        # artificial delay
        elif request.experiment_type == ExperimentType.NETWORK_DELAY:
            target_container.exec_run(
                f"tc qdisc add dev eth0 root netem delay {request.intensity}ms"
            )
            await asyncio.sleep(request.duration_seconds)
            # clean it up after experiment ends
            target_container.exec)run(
                "tc qdisc del dev eth0 root"
            )
            result = f"Network delay of {request.intensity}ms for {request.duration_seconds}s"
        # "one must imagine sisyphus happy"
        # resource exhaustion, noisy neighbor, runaway process
        # cpu stress
        elif request.experiment_type == ExperimentType.CPU_STRESS:
            target_container.exec_run(
                f"stress --cpu 2 --timeout {request.duration_seconds}",
                detach=True
            )
            result = f"CPU stress for {request.duration_seconds}s"

        # record success metrics
        EXPERIMENTS_RUN.labels(
            experiment_type=request.experiment_type.value,
            target=request.target_service,
            status="success"
        ).inc()

        # save to history
        experiment_record = {
            "timestamp": start_time.isoformat(),
            "target": request.target_service,
            "type": request.experiment_type.value,
            "duration": request.duration_seconds,
            "result": result,
            "status": "success"
        }
        experiment_history.append(experiment_record)

        return experiment_record

    except Exception as e:
        EXPERIMENTS_RUN.labels(
            experiment_type=request.experiment_type.value,
            target=request.target_service,
            status="failed"
        ).inc()

        raise HTTPException(status_code=500, detail=str(e))

# view experiment history
# for debugging and reporting
@app.get("/experiments")
async def get_experiments():
    return {"experiments": experiment_history}

# undo button
@app.post("/recover/{service_name}")
async def recover_service(service_name: str):
    # all=True shows all docker containers
    containers = docker_client.containers.list(
        all=True,
        filters="name": service_name}
    )

    if not containers:
        raise HTTPException(status_code=404, detail="Service not found")

    container = containers[0]

    if container.status != "running":
        container.start()
        return {"status": "recovered", "service": service_name}

    return {"status": "already running", "service": service_name}

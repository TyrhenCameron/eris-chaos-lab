from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import httpx
import asyncio
import yaml
import os
from datetime import datetime
from enum import Enum
from prometheus_client import Counter, generate_latest
from fastapi.responses import PlainTextResponse

app = FastAPI(title="ERIS Experiment Runner")

PROMETHEUS_URL = "http://prometheus:9090"
CHAOS_CONTROLLER_URL = "http://chaos-controller:8080"

EXPERIMENTS_DIR = "./experiments"

EXPERIMENTS_RUN = Counter(
    'experiment_runner_total',
    'Total experiments run',
    ['experiment_name', 'result'] # results can be pass/fail/aborted
)

# data models

class ExperimentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"

# baseline
class SteadyState(BaseModel):
    max_error_rate: float = 0.01  #1% error max
    max_latency_p95: float = 0.5 # 500ms max latency

# when to emergency stop the experiment
class AbortConditions(BaseModel):
    max_error_rate: float = 0.5 # abort if errors exceed 50%
    max_latency_p95: float = 5.0 #abort if latency exceeds 5 seconds

# the chaos to inject
class ChaosConfig(BaseModel):
    target_service: str
    experiment_type: str #container kill or pause etc
    duration_seconds: int = 30
    intensity: Optional[int] = 50

class Experiment(BaseModel):
    name: str
    description: str #what are we testing
    hypothesis: str # what we expect to happen
    steady_state: SteadyState # baseline conditions
    abort_conditions: AbortConditions # when to stop early
    chaos: ChaosConfig # what chaos to inject

class ExperimentResult(BaseModel):
    experiment_name: str
    status: ExperimentStatus
    hypothesis: str
    started_at: str
    ended_at: str
    duration_seconds: float
    steady_state_before: Dict[str, float] # metrics before
    steady_state_after: Dict[str, float] #metrics after chaos
    abort_triggered: bool
    abort_reason: Optional[str] = None
    passed: bool
    summary: str

async def query_prometheus(query: str) -> float:
    """
    Send a PromQL query to Prometheus and get the results.
    Returns 0.0 if no data or error.
    """

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # prometheus query API endpoint
            response = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query}
            )
            data = response.json()

            # dig into the nested response structure
            # prometheus gives us {status, data: {result: [{value: [timestamp, "value"]}]}}
            if data["status"] == "success" and data["data"]["result"]:
                value = float(data["data"]["result"][0]["value"][1])
                return value
            return 0.0
        except Exception as e:
            print(f"Prometheus query failed: {e}")
            return 0.0

async def get_current_metrics() -> Dict[str, float]:
    """
    Get all the metrics we care about for steady state checking.
    Returns a dictionary of metric names to values.
    """
    # calculate error rate: failed requests / total requests
    error_rate_query = """
        sum(rate(loadgen_requests_total{status="failed"}[1m]))
        /
        sum(rate(loadgen_requests_total[1m]))
    """

    # get 95th percentile latency
    latency_query = """
        histogram_quantile(0.95, rate(loadgen_response_time_seconds_bucket[1m]))
    """

    error_rate = await query_prometheus(error_rate_query)
    latency_p95 = await query_prometheus(latency_query)

    # handle NaN
    if error_rate != error_rate:
        error_rate = 0.0
    if latency_p95 != latency_p95:
        latency_p95 = 0.0
    return {
        "error_rate": error_rate,
        "latency_p95": latency_p95
    }

# steady state checker
async def check_steady_state(steady_state: SteadyState) -> tuple[bool, Dict[str, float]]:
    """
    Check if the system is currently in steady state (healthy).
    Returns (is_healthy, current_metrics).
    """
    metrics = await get_current_metrics()

    is_healthy = (
        metrics["error_rate"] <= steady_state.max_error_rate and
        metrics["latency_p95"] <= steady_state.max_latency_p95
    )

    return is_healthy, metrics

async def check_abort_conditions(abort_conditions: AbortConditions) -> tuple[bool, str]:
    """
    Check if we should abort the experiment.
    Returns (should_abort, reason).
    """
    metrics = await get_current_metrics()

    if metrics["error_rate"] > abort_conditions.max_error_rate:
        return True, f"Error rate {metrics['error_rate']:.2%} exceeded threshold {abort_conditions.max_error_rate:.2%}"

    if metrics["latency_p95"] > abort_conditions.max_latency_p95:
        return True, f"Latency {metrics['latency_p95']:.2f}s exceeded threshold {abort_conditions.max_latency_p95:.2f}s"

    return False, ""

async def inject_chaos(chaos: ChaosConfig) -> bool:
    """
    Call the chaos-controller to inject failure.
    Returns True if successful.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{CHAOS_CONTROLLER_URL}/experiment",
                json={
                    "target_service": chaos.target_service,
                    "experiment_type": chaos.experiment_type,
                    "duration_seconds": chaos.duration_seconds,
                    "intensity": chaos.intensity
                }
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to inject chaos: {e}")
            return False

async def recover_service(service_name: str) -> bool:
    """
    Call the chaos-controller to recover a killed service.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{CHAOS_CONTROLLER_URL}/recover/{service_name}"
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to recover service: {e}")
            return False

# core experiment runner
async def run_experiment(experiment: Experiment) -> ExperimentResult:
    """
    Run a complete a chaos experiment with steady state validation.
    Flow:
    1. Check steady before
    2. Inject chaos
    3. Monitor for abort conditions
    4. Wait for experiment duration
    5. Recover if needed
    6. Check steady state after
    7. Validate hypothesis
    8. Generate results
    """
    started_at = datetime.now()
    abort_triggered = False
    abort_reason = None

    # Step 1 - check state before chaos
    print(f"[{experiment.name}] Checking steady state before experiment...")
    is_healthy, metrics_before = await check_steady_state(experiment.steady_state)

    if not is_healthy:
        # if system is already unhealthy, don't run experiment
        return ExperimentResult(
            experiment_name=experiment.name,
            status=ExperimentStatus.ABORTED,
            hypothesis=experiment.hypothesis,
            started_at=started_at.isoformat(),
            ended_at=datetime.now().isoformat(),
            duration_seconds=0,
            steady_state_before=metrics_before,
            steady_state_after=metrics_before,
            abort_triggered=True,
            abort_reason="System not in steady state before experiment",
            passed=False,
            summary="Experiment aborted: system was unhealthy before chaos injection"
        )
    print(f"[{experiment.name}] Steady state OK. Injecting chaos...")

    # Step 2 - Inject chaos
    chaos_started = await inject_chaos(experiment.chaos)

    if not chaos_started:
        return ExperimentResult(
            experiment_name=experiment.name,
            status=ExperimentStatus.FAILED,
            hypothesis=experiment.hypothesis,
            started_at=started_at.isoformat(),
            ended_at=datetime.now().isoformat(),
            duration_seconds=0,
            steady_state_before=metrics_before,
            steady_state_after=metrics_before,
            abort_triggered=False,
            passed=False,
            summary="Experiment failed: could not inject chaos"
        )

    # Step 3 - Monitor during chaos

    print(f"[{experiment.name}] Chaos injected. Monitoring for {experiment.chaos.duration_seconds}s...")

    check_interval = 2 # check every 2 seconds
    elapsed = 0

    while elapsed < experiment.chaos.duration_seconds:
        await asyncio.sleep(check_interval)
        elapsed += check_interval

        should_abort, reason = await check_abort_conditions(experiment.abort_conditions)

        if should_abort:
            print(f"[{experiment.name}] ABORT triggered: {reason}")
            abort_triggered = True
            abort_reason = reason

            #try to recover service
            await recover_service(experiment.chaos.target_service)
            break

    # Step 4 - wait for system to stabilize
    print(f"[{experiment.name}] Chaos complete. Waiting for system to stabilize...")

    await asyncio.sleep(5) # give the system 5 seconds to recover

    # Step 5 - recover service if it was killed
    if experiment.chaos.experiment_type == "container_kill":
        await recover_service(experiment.chaos.target_service)
        await asyncio.sleep(10) # wait for service to fully start

    #Step 6 - check steady state after chaos
    print(f"[{experiment.name}] Checking state after experiment...")
    is_healthy_after, metrics_after = await check_steady_state(experiment.steady_state)

    ended_at = datetime.now()
    duration = (ended_at - started_at).total_seconds()

    # Step 7 - determine pass/fail
    if abort_triggered:
        status = ExperimentStatus.ABORTED
        passed = False
        summary = f"Experiment aborted: {abort_reason}"
    elif is_healthy_after:
        status = ExperimentStatus.PASSED
        passed = True
        summary = f"Hypothesis validated: system recovered to steady state after chaos"
    else:
        status = ExperimentStatus.FAILED
        passed = False
        summary = f"Hypothesis failed: system did not return to steady state after chaos"

    # record metrics
    EXPERIMENTS_RUN.labels(
        experiment_name=experiment.name,
        result=status.value
    ).inc()

    print(f"[{experiment.name}] Experiment complete: {status.value}")

    return ExperimentResult(
        experiment_name=experiment.name,
        status=status,
        hypothesis=experiment.hypothesis,
        started_at=started_at.isoformat(),
        ended_at=ended_at.isoformat(),
        duration_seconds=duration,
        steady_state_before=metrics_before,
        steady_state_after=metrics_after,
        abort_triggered=abort_triggered,
        abort_reason=abort_reason,
        passed=passed,
        summary=summary,
    )

def load_experiment_from_yaml(file_path: str) -> Experiment:
    """
    Load an experiment definition from a YAML file.
    """

    with open(file_path, 'r') as f:
        data = yaml.safe_load(f)

    return Experiment(
        name=data['name'],
        description=data['description'],
        hypothesis=data['hypothesis'],
        steady_state=SteadyState(**data['steady_state']),
        abort_conditions=AbortConditions(**data['abort_conditions']),
        chaos=ChaosConfig(**data['chaos'])
    )

def list_available_experiments() -> List[str]:
    """
    List all YAML experiment files in the experiments directory.
    """
    if not os.path.exists(EXPERIMENTS_DIR):
        return []

    return [
        f.replace('.yaml', '')
        for f in os.listdir(EXPERIMENTS_DIR)
        if f.endswith('.yaml')
    ]

# API Endpoints

# store results of experiments we've run
experiment_history: List[ExperimentResult] = []

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "experiment-runner"}

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return generate_latest()

@app.get("/experiments")
async def list_experiments():
    """
    List all available experiment definitions.
    """

    return {"experiments": list_available_experiments()}

@app.get("/experiments/{name}")
async def get_experiment(name: str):
    """
    Get details of a specific experiment definition.
    """
    file_path = f"{EXPERIMENTS_DIR}/{name}.yaml"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Experiment '{name}' not found")

    experiment = load_experiment_from_yaml(file_path)
    return experiment

@app.post("/run/{name}")
async def run_experiment_by_name(name: str):
    """
    Run an experiment by name (loads from YAML file).
    """
    file_path = f"{EXPERIMENTS_DIR}/{name}.yaml"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Experiment '{name}' not found")

    experiment = load_experiment_from_yaml(file_path)
    result = await run_experiment(experiment)
    experiment_history.append(result)
    return result

@app.post("/run")
async def run_experiment_inline(experiment: Experiment):
    """
    Run an experiment defined in the request body (no YAML file needed)
    """
    result = await run_experiment(experiment)
    experiment_history.append(result)
    return result

@app.get("/history")
async def get_history():
    """
    Get history of all experiments that have been run.
    """
    return {"history": experiment_history}

@app.get("/history/{name}")
async def get_history_by_name(name: str):
    """
    Get history for a specific experiment.
    """
    filtered = [r for r in experiment_history if r.experiment_name == name]
    return {"history": filtered}

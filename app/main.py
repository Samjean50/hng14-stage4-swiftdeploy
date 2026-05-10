# main.py — SwiftDeploy API service with Prometheus metrics
import os
import time
import random
import threading
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI()

# --- Startup state ---
START_TIME = time.time()
MODE = os.getenv("MODE", "stable")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_PORT = int(os.getenv("APP_PORT", "3000"))

# --- Chaos state ---
chaos_state = {"mode": None, "duration": 0, "rate": 0.0}
chaos_lock = threading.Lock()

# --- Metrics state ---
# These track raw counters and histogram buckets
metrics_lock = threading.Lock()

# http_requests_total — dict of (method, path, status_code) -> count
request_counters = {}

# http_request_duration_seconds — histogram
# Standard Prometheus buckets in seconds
BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
# bucket_counts[i] = number of requests that completed in <= BUCKETS[i] seconds
duration_buckets = [0] * len(BUCKETS)
duration_inf = 0       # requests that took longer than all buckets
duration_sum = 0.0     # sum of all durations (for average calculation)
duration_count = 0     # total number of timed requests


def record_request(method: str, path: str, status_code: int, duration: float):
    """
    Updates all metrics counters for a completed request.
    Called by the middleware after every request.
    """
    with metrics_lock:
        # Increment request counter for this label combination
        key = (method, path, str(status_code))
        request_counters[key] = request_counters.get(key, 0) + 1

        # Update histogram buckets
        # A histogram bucket le="0.1" counts ALL requests that took <= 0.1s
        # So we increment every bucket that is >= the actual duration
        global duration_inf, duration_sum, duration_count
        for i, bucket in enumerate(BUCKETS):
            if duration <= bucket:
                duration_buckets[i] += 1
        duration_inf += 1      # +inf bucket always increments
        duration_sum += duration
        duration_count += 1


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """
    Middleware runs before and after every request.
    Records timing and status code for metrics.
    Skips /metrics itself to avoid counting metric scrapes.
    """
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    # Don't record metrics scrapes in metrics — would skew the data
    if request.url.path != "/metrics":
        record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=duration
        )

    return response


def add_mode_header(response: JSONResponse) -> JSONResponse:
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    return response


def apply_chaos():
    with chaos_lock:
        current = dict(chaos_state)
    if current["mode"] == "slow":
        time.sleep(current["duration"])
    elif current["mode"] == "error":
        if random.random() < current["rate"]:
            response = JSONResponse(
                content={"error": "chaos error injection", "mode": MODE},
                status_code=500
            )
            return add_mode_header(response)
    return None


@app.get("/")
async def root():
    chaos_response = apply_chaos()
    if chaos_response:
        return chaos_response
    response = JSONResponse(content={
        "message": "SwiftDeploy API is running",
        "mode": MODE,
        "version": APP_VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })
    return add_mode_header(response)


@app.get("/healthz")
async def healthz():
    uptime = int(time.time() - START_TIME)
    response = JSONResponse(content={
        "status": "ok",
        "mode": MODE,
        "version": APP_VERSION,
        "uptime_seconds": uptime
    })
    return add_mode_header(response)


@app.post("/chaos")
async def chaos(request: Request):
    if MODE != "canary":
        return JSONResponse(
            content={"error": "chaos only available in canary mode"},
            status_code=403
        )
    body = await request.json()
    chaos_mode = body.get("mode")
    with chaos_lock:
        if chaos_mode == "slow":
            chaos_state["mode"] = "slow"
            chaos_state["duration"] = int(body.get("duration", 2))
            chaos_state["rate"] = 0.0
            msg = f"Chaos: slow mode {chaos_state['duration']}s"
        elif chaos_mode == "error":
            chaos_state["mode"] = "error"
            chaos_state["rate"] = float(body.get("rate", 0.5))
            chaos_state["duration"] = 0
            msg = f"Chaos: error mode {chaos_state['rate']*100:.0f}%"
        elif chaos_mode == "recover":
            chaos_state["mode"] = None
            chaos_state["duration"] = 0
            chaos_state["rate"] = 0.0
            msg = "Chaos cancelled"
        else:
            return JSONResponse(
                content={"error": f"unknown chaos mode: {chaos_mode}"},
                status_code=400
            )
    response = JSONResponse(content={"message": msg, "chaos_state": dict(chaos_state)})
    return add_mode_header(response)


@app.get("/metrics")
async def metrics():
    """
    Exposes metrics in Prometheus text format.
    This is the standard format that Prometheus, Grafana, and CLI tools
    can scrape and parse.

    Format: metric_name{label="value"} numeric_value
    Lines starting with # are comments/metadata
    """
    uptime = time.time() - START_TIME

    # Determine numeric values for state metrics
    # app_mode: 0=stable, 1=canary
    mode_value = 1 if MODE == "canary" else 0

    # chaos_active: 0=none, 1=slow, 2=error
    with chaos_lock:
        cm = chaos_state["mode"]
    if cm == "slow":
        chaos_value = 1
    elif cm == "error":
        chaos_value = 2
    else:
        chaos_value = 0

    lines = []

    # --- app_uptime_seconds ---
    lines.append("# HELP app_uptime_seconds Seconds since process started")
    lines.append("# TYPE app_uptime_seconds gauge")
    lines.append(f"app_uptime_seconds {uptime:.2f}")

    # --- app_mode ---
    lines.append("# HELP app_mode Current deployment mode (0=stable 1=canary)")
    lines.append("# TYPE app_mode gauge")
    lines.append(f"app_mode {mode_value}")

    # --- chaos_active ---
    lines.append("# HELP chaos_active Active chaos mode (0=none 1=slow 2=error)")
    lines.append("# TYPE chaos_active gauge")
    lines.append(f"chaos_active {chaos_value}")

    # --- http_requests_total ---
    lines.append("# HELP http_requests_total Total HTTP requests by method path status")
    lines.append("# TYPE http_requests_total counter")
    with metrics_lock:
        for (method, path, status), count in request_counters.items():
            lines.append(
                f'http_requests_total{{method="{method}",path="{path}",'
                f'status_code="{status}"}} {count}'
            )

    # --- http_request_duration_seconds histogram ---
    lines.append("# HELP http_request_duration_seconds Request duration in seconds")
    lines.append("# TYPE http_request_duration_seconds histogram")
    with metrics_lock:
        for i, bucket in enumerate(BUCKETS):
            lines.append(
                f'http_request_duration_seconds_bucket{{le="{bucket}"}} '
                f'{duration_buckets[i]}'
            )
        lines.append(
            f'http_request_duration_seconds_bucket{{le="+Inf"}} {duration_inf}'
        )
        lines.append(
            f'http_request_duration_seconds_sum {duration_sum:.6f}'
        )
        lines.append(
            f'http_request_duration_seconds_count {duration_count}'
        )

    # Prometheus format requires a trailing newline
    return PlainTextResponse(
        content="\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=APP_PORT)

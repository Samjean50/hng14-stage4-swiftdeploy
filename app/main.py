# main.py — The API service for SwiftDeploy
# Runs in either stable or canary mode via MODE environment variable
# Three endpoints: /, /healthz, /chaos

import os
import time
import random
import threading
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# --- Global state ---
# These persist across requests within the same container lifecycle

# Record when the process started — used for uptime calculation
START_TIME = time.time()

# Read mode from environment — defaults to stable if not set
# MODE is injected by docker-compose from the manifest
MODE = os.getenv("MODE", "stable")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_PORT = int(os.getenv("APP_PORT", "3000"))

# Chaos state — tracks active chaos configuration
# None means no chaos active
chaos_state = {
    "mode": None,      # "slow", "error", or None
    "duration": 0,     # seconds to sleep for "slow" mode
    "rate": 0.0,       # error rate for "error" mode (0.0 to 1.0)
}
# Lock for thread-safe chaos state access
chaos_lock = threading.Lock()


def add_mode_header(response: JSONResponse) -> JSONResponse:
    """
    Adds X-Mode header to every response in canary mode.
    Called by every endpoint handler.
    """
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    return response


def apply_chaos():
    """
    Applies active chaos configuration to the current request.
    Returns a JSONResponse if chaos should short-circuit the request,
    or None if the request should proceed normally.
    """
    with chaos_lock:
        current_chaos = dict(chaos_state)

    if current_chaos["mode"] == "slow":
        # Sleep for the configured duration before responding
        time.sleep(current_chaos["duration"])

    elif current_chaos["mode"] == "error":
        # Return 500 on approximately 'rate' fraction of requests
        # random.random() returns 0.0 to 1.0 uniformly
        # if rate=0.5, half of all calls will be < 0.5
        if random.random() < current_chaos["rate"]:
            response = JSONResponse(
                content={"error": "chaos error injection", "mode": MODE},
                status_code=500
            )
            return add_mode_header(response)

    return None  # No chaos short-circuit — proceed normally


@app.get("/")
async def root():
    """
    Welcome endpoint — returns mode, version, and current timestamp.
    Chaos is applied here if active.
    """
    chaos_response = apply_chaos()
    if chaos_response:
        return chaos_response

    response = JSONResponse(content={
        "message": f"SwiftDeploy API is running",
        "mode": MODE,
        "version": APP_VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })
    return add_mode_header(response)


@app.get("/healthz")
async def healthz():
    """
    Liveness health check endpoint.
    Returns status and process uptime in seconds.
    Used by Docker health check and swiftdeploy deploy/promote commands.
    Never applies chaos — health checks must always be reliable.
    """
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
    """
    Chaos injection endpoint.
    Only active in canary mode — returns 403 in stable mode.
    Accepts JSON body describing the chaos to inject.
    """
    # Chaos endpoint is only available in canary mode
    if MODE != "canary":
        response = JSONResponse(
            content={"error": "chaos endpoint only available in canary mode"},
            status_code=403
        )
        return response

    body = await request.json()
    chaos_mode = body.get("mode")

    with chaos_lock:
        if chaos_mode == "slow":
            # Inject latency — sleep N seconds before responding
            chaos_state["mode"] = "slow"
            chaos_state["duration"] = int(body.get("duration", 2))
            chaos_state["rate"] = 0.0
            msg = f"Chaos activated: slow mode, {chaos_state['duration']}s delay"

        elif chaos_mode == "error":
            # Inject errors — return 500 on a fraction of requests
            chaos_state["mode"] = "error"
            chaos_state["rate"] = float(body.get("rate", 0.5))
            chaos_state["duration"] = 0
            msg = f"Chaos activated: error mode, {chaos_state['rate']*100:.0f}% error rate"

        elif chaos_mode == "recover":
            # Cancel all active chaos
            chaos_state["mode"] = None
            chaos_state["duration"] = 0
            chaos_state["rate"] = 0.0
            msg = "Chaos cancelled — service recovering"

        else:
            response = JSONResponse(
                content={"error": f"unknown chaos mode: {chaos_mode}"},
                status_code=400
            )
            return add_mode_header(response)

    response = JSONResponse(content={
        "message": msg,
        "chaos_state": dict(chaos_state)
    })
    return add_mode_header(response)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=APP_PORT)

# SwiftDeploy

A declarative deployment CLI that generates Nginx and Docker Compose
configurations from a single `manifest.yaml` file, enforces safety
policies via Open Policy Agent, and provides live observability through
Prometheus metrics and a terminal dashboard.

## Architecture
manifest.yaml (single source of truth)
↓
swiftdeploy init
↓
generates nginx.conf + docker-compose.yml
↓
swiftdeploy deploy
↓ queries OPA (pre-deploy policy gate)
↓
Running stack:
Nginx (port 8080) → API service (port 3000, internal)
OPA (port 8181, localhost only)
↓
swiftdeploy status — live metrics dashboard
swiftdeploy audit  — generates audit_report.md

## Prerequisites

- Docker 24+
- Docker Compose v2+
- Python 3.8+
- pip packages: `pyyaml jinja2 requests`

## Setup from scratch

```bash
# Clone the repo
git clone https://github.com/Samjean50/hng14-stage4-swiftdeploy.git
cd hng14-stage4-swiftdeploy

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install CLI dependencies
pip install pyyaml jinja2 requests

# Build the API image
docker build -t swift-deploy-1-node:latest ./app

# Deploy
./swiftdeploy deploy
```

Successful startup looks like:
=== SwiftDeploy Deploy ===
→ Loading manifest...
→ Rendering templates...
✓ Generated nginx.conf
✓ Generated docker-compose.yml
✓ init complete
→ Starting stack...
✔ Container ...-opa-1     Started
✔ Container ...-api-1     Healthy
✔ Container ...-nginx-1   Started
→ Waiting for OPA to start...
✓ OPA is ready
→ Running OPA policy checks (pre-deploy)...
✓ Infrastructure policy: PASS — host is healthy
→ Waiting for health checks...
✓ Service healthy — mode=stable uptime=8s
✓ DEPLOY COMPLETE
API:     http://localhost:8080
Health:  http://localhost:8080/healthz
Metrics: http://localhost:8080/metrics

## Subcommands

| Command | Description |
|---------|-------------|
| `./swiftdeploy init` | Generate nginx.conf and docker-compose.yml from manifest |
| `./swiftdeploy validate` | Run 5 pre-flight checks |
| `./swiftdeploy deploy` | Init + OPA policy gate + start stack + health check |
| `./swiftdeploy promote canary` | Switch to canary mode with rolling restart |
| `./swiftdeploy promote stable` | Switch back to stable (with canary safety check) |
| `./swiftdeploy status` | Live metrics dashboard with policy compliance |
| `./swiftdeploy audit` | Generate audit_report.md from history |
| `./swiftdeploy teardown` | Remove all containers and networks |
| `./swiftdeploy teardown --clean` | Remove stack and delete generated files |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Welcome message with mode, version, timestamp |
| `/healthz` | GET | Health check — status and uptime |
| `/metrics` | GET | Prometheus metrics |
| `/chaos` | POST | Inject chaos (canary mode only) |

## Metrics Exposed

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Requests by method, path, status_code |
| `http_request_duration_seconds` | Histogram | Request latency with standard buckets |
| `app_uptime_seconds` | Gauge | Seconds since process started |
| `app_mode` | Gauge | 0=stable, 1=canary |
| `chaos_active` | Gauge | 0=none, 1=slow, 2=error |

## OPA Policy Enforcement

All allow/deny decisions live in OPA — the CLI never decides itself.

### Infrastructure policy (pre-deploy)

Blocks deployment if host resources are insufficient:
Disk free < 10GB     → blocked
CPU load > 30.0      → blocked
Memory free < 10%    → blocked

### Canary safety policy (pre-promote)

Blocks promotion from canary to stable if service is degraded:
Error rate > 1%      → blocked
P99 latency > 500ms  → blocked

Thresholds are in `policies/data.json` — never hardcoded in Rego files.
To change a threshold, edit `data.json` only. No policy files need touching.

### Triggering a policy violation (demo)

```bash
# Temporarily lower CPU threshold to force a block
# Edit policies/data.json: "max_cpu_load": 0.1
./swiftdeploy teardown
./swiftdeploy deploy
# → Deploy blocked: CPU load X.XX exceeds maximum 0.10

# Restore threshold
# Edit policies/data.json: "max_cpu_load": 30.0
./swiftdeploy deploy
```

## Chaos Engineering

```bash
# Promote to canary first
./swiftdeploy promote canary

# Inject 50% error rate
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "error", "rate": 0.5}'

# Inject slow responses (3 second delay)
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "slow", "duration": 3}'

# Recover
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "recover"}'
```

## Live Status Dashboard

```bash
./swiftdeploy status
```

Refreshes every 3 seconds showing:
- Current mode and chaos state
- Real-time req/s and P99 latency
- Error rate
- OPA policy compliance (pass/fail per domain)

Every scrape is appended to `history.jsonl` for the audit trail.

## Audit Report

```bash
./swiftdeploy audit
```

Generates `audit_report.md` with:
- Full timeline of all events
- Policy violations table
- Mode changes table

## Project Structure
manifest.yaml          ← only file you edit manually
swiftdeploy            ← the CLI tool
app/
main.py              ← FastAPI service with /metrics
Dockerfile           ← builds swift-deploy-1-node:latest
requirements.txt
templates/
nginx.conf.j2        ← Nginx template
docker-compose.yml.j2 ← Compose template
policies/
infrastructure.rego  ← host health policy
canary.rego          ← canary safety policy
data.json            ← all thresholds (edit here, not in Rego)
nginx.conf             ← GENERATED — do not edit
docker-compose.yml     ← GENERATED — do not edit
history.jsonl          ← audit trail (appended by status)
audit_report.md        ← GENERATED by swiftdeploy audit
README.md

## Blog Post

Full technical deep dive covering design decisions, OPA policy logic,
chaos injection, and lessons learned:

[Published blog post](https://medium.com/@samson.bakare50/how-i-built-swiftdeploy-a-tool-that-writes-its-own-infrastructure-files-and-refuses-to-deploy-a888905b208b)

## GitHub Repository

https://github.com/Samjean50/hng14-stage4-swiftdeploy
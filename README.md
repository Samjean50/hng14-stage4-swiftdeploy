# SwiftDeploy

A declarative deployment CLI that generates Nginx and Docker Compose
configurations from a single manifest.yaml file.

## Prerequisites
- Docker 24+
- Docker Compose v2+
- Python 3.8+

## Setup

```bash
# Build the API image first
docker build -t swift-deploy-1-node:latest ./app

# Install Python deps for the CLI
pip install pyyaml jinja2 requests
```

## Subcommands

| Command | Description |
|---------|-------------|
| `./swiftdeploy init` | Generate configs from manifest |
| `./swiftdeploy validate` | Run 5 pre-flight checks |
| `./swiftdeploy deploy` | Init + start stack + health check |
| `./swiftdeploy promote canary` | Switch to canary mode |
| `./swiftdeploy promote stable` | Switch back to stable mode |
| `./swiftdeploy teardown` | Remove stack |
| `./swiftdeploy teardown --clean` | Remove stack + delete generated files |

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| / | GET | Welcome + mode + version + timestamp |
| /healthz | GET | Status + uptime in seconds |
| /chaos | POST | Inject chaos (canary mode only) |

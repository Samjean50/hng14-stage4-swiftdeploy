# Multi-stage build keeps the final image small
# Builder stage installs dependencies
FROM python:3.12-alpine AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final stage — only what's needed to run
FROM python:3.12-alpine

# Create non-root user — running as root in containers is a security risk
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Fix ownership
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Health check — Docker uses this to mark container healthy/unhealthy
HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/healthz')" || exit 1

# These are overridden by docker-compose environment section
ENV MODE=stable
ENV APP_VERSION=1.0.0
ENV APP_PORT=3000

EXPOSE 3000

CMD ["python", "-u", "main.py"]

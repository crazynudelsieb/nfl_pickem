# Multi-stage build for optimized image size
# Stage 1: Builder stage
FROM python:3.14.2-slim AS builder

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies to a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.14.2-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create non-root user first
RUN useradd --create-home --no-log-init --shell /bin/bash --uid 1000 app \
    && mkdir -p /app/logs \
    && chown -R app:app /app

# Copy application code
COPY --chown=app:app . .

# Make scripts executable
RUN chmod +x /app/scripts/entrypoint.sh /app/scripts/startup.py

# Switch to non-root user
USER app

# Expose port
EXPOSE 5000

# Health check with improved parameters
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Start command with entrypoint
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["gunicorn", "-k", "eventlet", "-w", "1", "--timeout", "120", "--worker-connections", "1000", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info", "run:app"]
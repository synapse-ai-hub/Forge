# syntax=docker/dockerfile:1

# ==============================================================================
# Stage 1 — Build frontend (Vite + TypeScript)
# ==============================================================================
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

# Copy dependency manifests first for better layer caching
COPY frontend/package*.json ./
RUN npm ci

# Copy the rest of the frontend source
COPY frontend/ ./

# Build in production mode (API calls resolve to same origin by default)
ARG VITE_MODE=prod
ARG VITE_URL_DEV=
ARG VITE_URL_PROD=
ENV VITE_MODE=$VITE_MODE \
    VITE_URL_DEV=$VITE_URL_DEV \
    VITE_URL_PROD=$VITE_URL_PROD

RUN npm run build

# ==============================================================================
# Stage 2a — Backend base (shared code, no frontend yet)
# ==============================================================================
FROM python:3.12-slim AS backend-base

WORKDIR /app

# Prevent Python from writing .pyc and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (if any — keep slim)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Expose the application port
EXPOSE 8000

# ==============================================================================
# Stage 2b — Backend only (for ACI / separated deployments)
# ==============================================================================
FROM backend-base AS backend-only

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ==============================================================================
# Stage 2c — Autocontained (backend + frontend static files)
# ==============================================================================
FROM backend-base AS autocontained

# Copy built frontend from Stage 1 (triggered by main.py catch-all)
COPY --from=frontend-build /app/frontend/dist/ ./frontend/dist/

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

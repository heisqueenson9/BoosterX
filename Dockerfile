# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Backend & Production Runtime
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application code
COPY backend/ backend/

# Copy built frontend dist into frontend/dist for Flask static serving
COPY --from=frontend-builder /app/frontend/dist frontend/dist

ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=backend.app:create_app()
EXPOSE 5000

ENV PORT=5000
CMD ["sh", "-c", "flask db upgrade && gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 'backend.app:create_app()'"]

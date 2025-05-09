# Stage 1: Build stage - Install dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy only pyproject.toml and poetry.lock to leverage Docker cache
COPY pyproject.toml poetry.lock ./

# Install dependencies using poetry
# --no-dev: Do not install development dependencies
# --no-interaction: Do not ask any interactive questions
# --no-ansi: Disable ANSI output
RUN poetry config virtualenvs.create false && poetry install --no-dev --no-interaction --no-ansi

# Stage 2: Runtime stage - Create the final slim image
FROM python:3.11-slim

WORKDIR /app

# Copy installed dependencies from the builder stage
COPY --from=builder /app /app

# Copy the application code
# Assuming the Dockerfile is in src/score/ and app.py, dummy_model.py are in the same directory
COPY . .

# Set environment variables (can be overridden at runtime)
ENV PYTHONUNBUFFERED=1 \
    APP_MODULE="app:app" \
    GUNICORN_CONF="/app/gunicorn_conf.py" \
    HOST="0.0.0.0" \
    PORT="80" \
    LOG_LEVEL="info"

# Expose the port the app runs on
EXPOSE 80

# Add a healthcheck to ensure the application is running correctly
# It will hit the /health endpoint of the FastAPI app
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${PORT}/health || exit 1

# Command to run the application using Gunicorn with Uvicorn workers
# The gunicorn_conf.py will define the number of workers, etc.
CMD ["gunicorn", "--config", "$GUNICORN_CONF", "$APP_MODULE"]

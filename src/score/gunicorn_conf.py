import os
import multiprocessing

# Gunicorn configuration file

# Host and port to bind to
# These can be overridden by environment variables HOST and PORT if set
host = os.environ.get("HOST", "0.0.0.0")
port = os.environ.get("PORT", "80")
bind = f"{host}:{port}"

# Worker class for Uvicorn
worker_class = "uvicorn.workers.UvicornWorker"

# Number of worker processes
# The general recommendation is (2 * number of CPU cores) + 1
# For a Fargate task with 0.5 vCPU, 1 worker might be appropriate to start.
# For 1 vCPU, 2-3 workers.
# This can be tuned based on load testing.
workers = int(os.environ.get("GUNICORN_WORKERS", (multiprocessing.cpu_count() * 2) + 1))
if workers > 4: # Cap workers for small instances
    workers = 4 
if os.environ.get("FARGATE_CPU") == "512": # 0.5 vCPU
    workers = 1
elif os.environ.get("FARGATE_CPU") == "1024": # 1 vCPU
    workers = 2


# Logging
# Log level can be overridden by LOG_LEVEL environment variable
loglevel = os.environ.get("LOG_LEVEL", "info")
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr

# Worker timeout (seconds)
# Workers silent for more than this period are killed and restarted.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))

# Keep alive
# The number of seconds to wait for requests on a Keep-Alive connection.
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", 2))

# Reload
# Restart workers when code changes (useful for development, disable in production)
# reload = os.environ.get("GUNICORN_RELOAD", "false").lower() == "true"

print(f"Gunicorn config: bind={bind}, workers={workers}, loglevel={loglevel}")

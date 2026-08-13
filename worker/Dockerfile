FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir -r /app/worker/requirements.txt
COPY worker /app/worker

ENV BACKEND_URL=http://host.docker.internal:8000 \
    WORKER_HEALTH_PORT=8081
EXPOSE 8081
CMD ["python", "-m", "worker.worker"]

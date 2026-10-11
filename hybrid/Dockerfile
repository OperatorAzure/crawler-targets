# Build context is the repo root (see docker-compose.yml) so the shared core can be copied in
FROM python:3.11-slim
WORKDIR /app
COPY hybrid/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /shared
COPY hybrid/ .
ENV GOWORK_DATA_DIR=/data PYTHONUNBUFFERED=1
# One process: sessions are held in memory
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]

# Build context is the repo root (see docker-compose.yml) so the shared core can be copied in
FROM python:3.11-slim
WORKDIR /app
COPY pure-spa/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /shared
COPY pure-spa/backend/ .
ENV GOWORK_DATA_DIR=/data PYTHONUNBUFFERED=1
# One process: revoked refresh tokens are held in memory
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8004"]

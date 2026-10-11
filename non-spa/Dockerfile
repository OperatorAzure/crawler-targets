# Build context is the repo root (see docker-compose.yml) so the shared core can be copied in
FROM python:3.11-slim
WORKDIR /app
COPY non-spa/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /shared
COPY non-spa/ .
ENV GOWORK_DATA_DIR=/data PYTHONUNBUFFERED=1
# Single worker: sessions are cookie-based but the database is rebuilt per process on start
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8001", "app:app"]

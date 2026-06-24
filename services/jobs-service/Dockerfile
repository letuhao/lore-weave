# Unified Job Control Plane P2 — jobs-service (central job projection + read API
# + SSE). Build context is the repo root (set in docker-compose.yml) so we can
# COPY the local SDKs alongside the service code. Reference: campaign-service.
FROM python:3.12-slim

WORKDIR /app

COPY services/jobs-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the local SDKs — loreweave_jobs (the canonical job contract +
# BaseProjectionConsumer this service consumes the job-event stream with) +
# loreweave_obs (tracing parity). jobs-service makes NO provider calls — it
# only projects job events + routes control to per-service APIs (P3).
COPY sdks/python /sdk
RUN pip install --no-cache-dir /sdk

COPY services/jobs-service/app/ ./app/

ENV PORT=8096
EXPOSE 8096

HEALTHCHECK --interval=5s --timeout=3s --start-period=15s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8096/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

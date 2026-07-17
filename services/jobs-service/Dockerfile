# Unified Job Control Plane P2 — jobs-service (central job projection + read API
# + SSE). Build context is the repo root (set in docker-compose.yml) so we can
# COPY the local SDKs alongside the service code. Reference: campaign-service.
FROM python:3.12-slim
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override ONLY when the local network blocks PyPI (some ISPs reset the
# connection mid-download, which fails any not-yet-cached pip layer):
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

COPY services/jobs-service/requirements.txt .
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

# Install the local SDKs — loreweave_jobs (the canonical job contract +
# BaseProjectionConsumer this service consumes the job-event stream with) +
# loreweave_obs (tracing parity). jobs-service makes NO provider calls — it
# only projects job events + routes control to per-service APIs (P3).
COPY sdks/python /sdk
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk

COPY services/jobs-service/app/ ./app/

ENV PORT=8096
EXPOSE 8096

HEALTHCHECK --interval=5s --timeout=3s --start-period=15s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8096/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

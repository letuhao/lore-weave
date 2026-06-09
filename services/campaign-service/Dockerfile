# Auto-Draft Factory S1 — campaign-service. Build context is the repo root
# (set in docker-compose.yml) so we can COPY the local SDKs alongside the
# service code. Reference impl: services/translation-service/Dockerfile.
FROM python:3.12-slim

WORKDIR /app

COPY services/campaign-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the local SDKs (loreweave_obs for tracing parity with the other
# Python services). campaign-service makes NO direct provider calls — it
# only drives the existing per-service job APIs over internal-token.
COPY sdks/python /sdk
RUN pip install --no-cache-dir /sdk

COPY services/campaign-service/app/ ./app/

ENV PORT=8095
EXPOSE 8095

HEALTHCHECK --interval=5s --timeout=3s --start-period=15s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8095/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

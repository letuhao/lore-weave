# Phase 5e-α: build context bumped to repo root so we can COPY the
# Python SDK alongside service code. Mirrors chat-service + translation-
# service patterns. docker-compose.yml passes `context: ..` +
# `dockerfile: services/video-gen-service/Dockerfile`.
FROM python:3.13-slim
# Build-time Python package index. Defaults to PyPI — CI and production builds are
# unchanged. Override ONLY when the local network blocks PyPI (some ISPs reset the
# connection mid-download, which fails any not-yet-cached pip layer):
#   docker compose build --build-arg PIP_INDEX_URL=https://<mirror>/simple
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

# SDK install — Phase 5e-α (matches translation-service Phase 4c-α + chat-service pattern).
COPY sdks/python /sdk
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" /sdk

COPY services/video-gen-service/requirements.txt .
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

COPY services/video-gen-service/app/ app/

ENV HTTP_PORT=8088
EXPOSE 8088

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]

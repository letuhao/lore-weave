FROM python:3.12-slim

WORKDIR /app

# Build context = repo root (infra/docker-compose.yml sets `context: ..`), so
# COPY paths are repo-relative. C0 needs only the service code; the local
# loreweave_llm SDK (sdks/python) is added in a later cycle when LLM calls land.
COPY services/lore-enrichment-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/lore-enrichment-service/app/ ./app/

ENV PORT=8093
EXPOSE 8093

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8093/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

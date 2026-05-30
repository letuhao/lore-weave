FROM python:3.12-slim

WORKDIR /app

# Build context is the repo root (compose sets `context: ..`,
# `dockerfile: services/learning-service/Dockerfile`) to match the other
# Python services. learning-service makes NO LLM calls this cycle, so it does
# NOT copy the loreweave_llm SDK — keep the image lean.

COPY services/learning-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/learning-service/app/ ./app/

ENV PORT=8094
EXPOSE 8094

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8094/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

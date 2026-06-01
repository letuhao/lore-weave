FROM python:3.12-slim

WORKDIR /app

# Build context is the repo root (compose sets `context: ..`,
# `dockerfile: services/learning-service/Dockerfile`) to match the other
# Python services.

COPY services/learning-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Q1 (Production Eval + Feedback Flywheel): learning-service now hosts the
# quality plane and imports `loreweave_eval` (the lifted extraction-quality
# scorer: EvalResult, EvalSink, JudgePanel). Install the local SDK — same
# pattern as knowledge-service. It also brings loreweave_llm/extraction, which
# the online-eval consumer (phase Q4) will use to run the judge via the gateway.
COPY sdks/python /sdk
RUN pip install --no-cache-dir /sdk

COPY services/learning-service/app/ ./app/

ENV PORT=8094
EXPOSE 8094

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8094/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

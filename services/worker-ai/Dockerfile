# Phase 4b-γ: build context is the repo root (set in docker-compose.yml)
# so we can COPY the local SDKs alongside the service code. Reference
# impl: services/knowledge-service/Dockerfile (Phase 4a-α).
FROM python:3.12-slim

WORKDIR /app

COPY services/worker-ai/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the local SDKs. The pyproject ships two top-level packages:
#   - loreweave_llm — gateway client (streaming + async jobs)
#   - loreweave_extraction — Pass 2 extraction library (Phase 4b-α)
# Worker-ai uses both to run Pass 2 in-process via
# extract_pass2(llm_client, ...) instead of calling knowledge-service's
# legacy /extract-item HTTP endpoint.
COPY sdks/python /sdk
RUN pip install --no-cache-dir /sdk

COPY services/worker-ai/app/ ./app/

RUN adduser --system --group --no-create-home worker \
    && chown -R worker:worker /app
USER worker

CMD ["python", "-m", "app.main"]

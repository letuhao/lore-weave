FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN adduser --system --group --no-create-home worker \
    && chown -R worker:worker /app
USER worker

CMD ["python", "-m", "app.main"]

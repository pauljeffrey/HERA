FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY hera_io ./hera_io

ENV PYTHONPATH=/app
EXPOSE 8000
ENTRYPOINT ["python", "-m", "app.entrypoint"]

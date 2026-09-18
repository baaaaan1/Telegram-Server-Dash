FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY . .
RUN mkdir -p /app/data
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "bot"]

FROM base AS dev
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
RUN mkdir -p /app/data
CMD ["python", "-m", "bot"]
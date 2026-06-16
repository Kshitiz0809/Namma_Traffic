FROM python:3.11-slim

WORKDIR /app

# System deps kept minimal for Phase 1. GeoPandas (Phase 2+) needs GDAL/GEOS,
# which we add when that requirement actually lands, to keep this image lean.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

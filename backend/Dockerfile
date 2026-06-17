# IMPORTANT: build context must be the REPO ROOT, not backend/ —
# e.g. `docker build -f backend/Dockerfile .` from the repo root.
# The app's PROJECT_ROOT path logic (backend/app/*/*.py: `parents[3]`)
# expects ml/, data/, docs/ as siblings of backend/ inside the image,
# mirroring the real repo layout. Render's "Root Directory" setting
# should be left at the repo root for this reason (see docs/deployment.md).
FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal. GeoPandas (if ever added) needs GDAL/GEOS,
# not currently required by anything on the frozen feature set.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --default-timeout=120 -r backend/requirements.txt

# Backend code.
COPY backend/ backend/
# Frozen model artifacts + risk-score scaling params (PHASE 3/5 outputs —
# must exist in the build context; see docs/deployment.md "Before you
# deploy" checklist. These are gitignored in the repo by design — regenerate
# locally via `python -m app.models.train` etc. before building this image).
COPY ml/models/ ml/models/
# Processed feature/target parquet (also gitignored — regenerate via
# `python -m app.features.build_features`).
COPY data/processed/ data/processed/
# Docs the API reads at request time (leaderboard.csv for /metrics,
# recommendation_rules.yaml for the rule engine) — these ARE committed.
COPY docs/leaderboard.csv docs/leaderboard.csv
COPY docs/recommendation_rules.yaml docs/recommendation_rules.yaml

WORKDIR /app/backend

EXPOSE 8000

# Render injects $PORT at runtime; default to 8000 for local `docker run`.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

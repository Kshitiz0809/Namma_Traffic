# Hugging Face Space Dockerfile.
# Reuses the already-built, already-pushed Docker Hub image (which bakes in
# ml/models/ and data/processed/ — see backend/Dockerfile) rather than
# rebuilding from source, since HF Spaces' git repo can't hold those
# gitignored binary artifacts without LFS.
# build-tag: 2026-06-18-temporal-distribution (bump this comment to force HF
# to re-pull `latest` instead of reusing a stale cached layer).
FROM kshitizs98/parking-intelligence-api:latest

# HF Spaces routes traffic to port 7860 by default (see README.md app_port).
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]

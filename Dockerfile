FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN useradd --create-home --uid 1000 appuser

# Dependencies first, so code changes don't invalidate this (slow) layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# All persistent state lives under /data - mount a volume there.
ENV ENVIRONMENT=production \
    DATA_DIR=/data/app \
    BACKUP_DIR=/data/backups \
    LOG_JSON=true \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/health\", timeout=4)"

ENTRYPOINT ["/entrypoint.sh"]
# One worker: the rate limiter and JSON stores live in process memory.
# --proxy-headers: trust X-Forwarded-For from the platform's load balancer for client IPs.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

# syntax=docker/dockerfile:1.7

# ---- 1. Web UI -----------------------------------------------------------------
FROM node:22-alpine AS ui
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Vite writes the bundle to /src/stallion/web/dist
RUN npm run build

# ---- 2. Python wheel with the UI embedded ----------------------------------------
FROM python:3.12-slim AS wheel
WORKDIR /src
RUN pip install --no-cache-dir build
COPY pyproject.toml README.md ./
COPY stallion ./stallion
COPY --from=ui /src/stallion/web/dist ./stallion/web/dist
RUN python -m build --wheel --outdir /wheels

# ---- 3. Runtime (Alpine keeps the image around 350 MB with a full-featured ffmpeg) ----
FROM python:3.12-alpine
# ffmpeg + fonts so burned-in subtitles render (Liberation is metric-compatible with Arial)
RUN apk add --no-cache ffmpeg fontconfig font-dejavu font-liberation tini \
 && adduser -D -u 1000 stallion \
 && mkdir -p /media /data \
 && chown stallion:stallion /media \
 && chmod 1777 /data
COPY --from=wheel /wheels/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

# /data is world-writable so the container can also run as the owner of the media folder (`user:`)
ENV PYTHONUNBUFFERED=1 \
    STALLION_HOST=0.0.0.0 \
    STALLION_PORT=8000 \
    STALLION_MEDIA_ROOTS=/media \
    STALLION_DATA_DIR=/data \
    XDG_CACHE_HOME=/data/.cache

USER stallion
VOLUME ["/media", "/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status != 200)"]
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["stallion", "serve"]

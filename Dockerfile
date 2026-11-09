# syntax=docker/dockerfile:1
# App QuandoPassa: interfaccia React (build) + API FastAPI in un'unica immagine.

FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Europe/Rome \
    GTFS_DIR=/srv/gtfs WEB_DIST=/srv/app/web
WORKDIR /srv/app
COPY api/requirements.txt .
RUN pip install -r requirements.txt
COPY api/quandopassa/ quandopassa/
COPY --from=web /web/dist/ web/
# feed predefinito dentro l'immagine; docker compose monta la cartella indicata da GTFS_DIR nel .env
COPY data/ /srv/gtfs/
RUN useradd --system --uid 10001 quandopassa && mkdir -p /srv/dati && chown quandopassa /srv/dati
USER quandopassa
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"
CMD ["uvicorn", "--factory", "quandopassa.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

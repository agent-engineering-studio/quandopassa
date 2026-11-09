# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Europe/Rome
WORKDIR /srv/inference
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY rules.py server.py ./
RUN useradd --system --uid 10002 inference
USER inference
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]

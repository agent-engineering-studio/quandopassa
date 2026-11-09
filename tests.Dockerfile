# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Europe/Rome
WORKDIR /srv
COPY api/requirements.txt api-req.txt
COPY inference/requirements.txt inf-req.txt
COPY mcp_server/requirements.txt mcp-req.txt
RUN pip install -r api-req.txt -r inf-req.txt -r mcp-req.txt pytest==8.4.2
COPY . .
CMD ["python", "-m", "pytest"]

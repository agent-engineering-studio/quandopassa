# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Europe/Rome
WORKDIR /srv/mcp
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY server.py .
RUN useradd --system --uid 10003 mcp
USER mcp
EXPOSE 8090
ENV MCP_TRANSPORT=http MCP_HOST=0.0.0.0 MCP_PORT=8090
CMD ["python", "server.py"]

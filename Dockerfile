FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    CHROMIUM_BIN=/usr/bin/chromium \
    COOKIES_PATH=/app/data/cookies.json \
    REDNOTE_HEADLESS=true \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=18060

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-noto-cjk \
    fonts-liberation \
    ca-certificates \
    tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rednote_mcp_server.py .

EXPOSE 18060

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "rednote_mcp_server.py"]

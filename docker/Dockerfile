FROM python:3.11-slim

LABEL maintainer="anders@nerq.ai"
LABEL description="Nerq Trust Oracle — AI agent trust verification"
LABEL org.opencontainers.image.source="https://github.com/zarq-ai/zarq-mcp-server"

RUN pip install --no-cache-dir nerq requests

WORKDIR /app

COPY entrypoint.py .

EXPOSE 8080

ENV NERQ_API_URL=https://nerq.ai

ENTRYPOINT ["python", "entrypoint.py"]

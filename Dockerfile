FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/ledgerly.db \
    INDEX_DIR=/app/data/index \
    UPLOAD_DIR=/app/data/uploads

COPY pyproject.toml README.md ./
COPY ledgerly ./ledgerly
RUN uv pip install --system .

RUN mkdir -p /app/data /app/logs
EXPOSE 8000

CMD ["sh", "-c", "python -m ledgerly.seed --if-empty && gunicorn -b 0.0.0.0:8000 -w 1 --threads 8 --timeout 120 ledgerly.wsgi:app"]

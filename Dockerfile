FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    librubberband-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN ffmpeg -filters 2>/dev/null | grep -q rubberband || \
    (echo "ERROR: rubberband not found in ffmpeg" && exit 1)

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY frontend/ ./frontend/

RUN mkdir -p /tmp/karaoke

EXPOSE 80

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "1"]

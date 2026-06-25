FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    librubberband-dev \
    supervisor \
    curl \
    wget \
    ca-certificates \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Verify rubberband filter is present in this ffmpeg build
RUN ffmpeg -filters 2>/dev/null | grep -q rubberband || \
    (echo "ERROR: rubberband not found in ffmpeg" && exit 1)

# Download bgutil-pot Rust binary — generates YouTube BotGuard PO tokens
# so yt-dlp works from cloud/VPS IPs without getting bot-blocked
RUN wget -q -O /usr/local/bin/bgutil-pot \
    https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/latest/download/bgutil-pot-linux-x86_64 \
    && chmod +x /usr/local/bin/bgutil-pot

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the yt-dlp plugin that connects yt-dlp to the bgutil-pot HTTP server
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider

COPY app/ ./app/
COPY frontend/ ./frontend/
COPY supervisord.conf /etc/supervisor/conf.d/karaoke.conf

RUN mkdir -p /tmp/karaoke /var/log/supervisor

# HF Spaces requires port 7860
EXPOSE 7860

CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Argus"
LABEL org.opencontainers.image.description="AI-Powered Smart Security System"
LABEL org.opencontainers.image.licenses="MIT"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    rclone \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY argus/ ./argus/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Data dirs
RUN mkdir -p data/clips data/events data/embeddings

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["python", "-m", "argus"]

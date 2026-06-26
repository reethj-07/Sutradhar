# Sutradhar app image (PRD §15). CPU base; the local dev path targets the
# operator's GPU directly. Finalized in M6.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg for audio decode/resample.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY sutradhar ./sutradhar
COPY mock_backend ./mock_backend
COPY clients ./clients

# Install the base package (CPU). The full local extras (faster-whisper, piper,
# onnxruntime, ollama client) are layered in M6 once pinned for the image.
RUN pip install --upgrade pip && pip install -e .

EXPOSE 8080 9100 8090
CMD ["python", "-m", "sutradhar.cli", "serve", "--host", "0.0.0.0"]

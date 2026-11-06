FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set up standard Hugging Face non-root user (UID 1000)
RUN useradd -m -u 1000 user

USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /home/user/app

# Install Python dependencies
COPY --chown=user ./requirements.txt /home/user/app/requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application files
COPY --chown=user . /home/user/app

# Expose HTTP port for health checks and keep-alive
EXPOSE 7860

# Run platform master service
CMD ["python", "-m", "src.main"]

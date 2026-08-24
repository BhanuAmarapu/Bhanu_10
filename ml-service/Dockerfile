FROM python:3.11-slim

# Install system dependencies (gcc, ffmpeg)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    ffmpeg \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/ml_data/hf_cache
ENV TRANSFORMERS_CACHE=/app/ml_data/hf_cache

# Command to run uvicorn
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

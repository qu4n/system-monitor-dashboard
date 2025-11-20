FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    lm-sensors \
    procps \
    sysstat \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir flask

# Copy application files
COPY app.py .
COPY templates ./templates

# Expose port
EXPOSE 5000

CMD ["python", "app.py"]

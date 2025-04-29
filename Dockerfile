# Use official Python slim image
FROM python:3.11-slim

# Install system dependencies needed for psycopg2 and other Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev git build-essential && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy and install Python dependencies (separate to cache it)
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 --retries 5 -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Run FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

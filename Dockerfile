# Use a Python base image that includes dependencies for matplotlib/numpy
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install system dependencies needed for visualization libraries (e.g., matplotlib)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    # The following are often needed for robust matplotlib on a headless server
    libblas-dev \
    liblapack-dev \
    gfortran \
    libfreetype6-dev \
    pkg-config \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app.py .

# Use Gunicorn to serve the Flask app for production-grade stability
# Gunicorn will listen on $PORT, which Cloud Run automatically sets.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:app

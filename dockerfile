# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Install system dependencies (nodejs + npm for cdxgen, git, curl)
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install cdxgen globally
RUN npm install -g @cyclonedx/cdxgen

# Create working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Make cbombench executable
RUN chmod +x /app/src/cbombench.py

# Default entrypoint
ENTRYPOINT ["python", "/app/src/cbombench.py"]
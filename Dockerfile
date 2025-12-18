FROM python:3.10-slim

# System dependencies (needed for SciPy, GeoPandas, Fiona, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    proj-data \
    proj-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Hugging Face uses port 7860
EXPOSE 7860

CMD ["hypercorn", "app:app", "--bind", "0.0.0.0:7860", "--workers", "1"]

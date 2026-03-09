FROM python:3.9-slim

WORKDIR /app

# Install system dependencies required by auto-sklearn
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    swig \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pin setuptools<70 to keep pkg_resources (required by auto-sklearn at import time)
# Newer setuptools (70+) removed pkg_resources
RUN pip install --no-cache-dir --upgrade pip wheel "setuptools<70"

# Install auto-sklearn with compatible versions
# auto-sklearn 0.15.0 needs scikit-learn >=0.24,<0.25
RUN pip install --no-cache-dir \
    flask \
    pandas \
    "numpy<2" \
    scikit-learn==0.24.2 \
    auto-sklearn==0.15.0

# Copy shared REST base and framework server
COPY docker/automl_rest_base.py /app/automl_rest_base.py
COPY docker/autosklearn/server.py /app/server.py

# Create models directory
RUN mkdir -p /app/models/autosklearn

EXPOSE 8085

CMD ["python", "server.py"]

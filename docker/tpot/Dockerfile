FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    flask \
    pandas \
    numpy \
    scikit-learn \
    tpot \
    xgboost \
    deap \
    update_checker \
    stopit

# Copy shared REST base and framework server
COPY docker/automl_rest_base.py /app/automl_rest_base.py
COPY docker/tpot/server.py /app/server.py

# Create models directory
RUN mkdir -p /app/models/tpot

EXPOSE 8084

CMD ["python", "server.py"]

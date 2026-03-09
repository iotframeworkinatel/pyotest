FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    flask \
    pandas \
    numpy \
    scikit-learn \
    autogluon.tabular[all]

# Copy shared REST base and framework server
COPY docker/automl_rest_base.py /app/automl_rest_base.py
COPY docker/autogluon/server.py /app/server.py

# Create models directory
RUN mkdir -p /app/models/autogluon

EXPOSE 8082

CMD ["python", "server.py"]

FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# PyCaret and scikit-learn are pinned to the versions recorded in
# models/archive/pycaret_*/model_binary/pycaret_model.pkl
RUN pip install --no-cache-dir \
    flask \
    pandas \
    numpy \
    scikit-learn==1.4.2 \
    pycaret==3.3.2

# Copy shared REST base and framework server
COPY docker/automl_rest_base.py /app/automl_rest_base.py
COPY docker/pycaret/server.py /app/server.py

# Create models directory
RUN mkdir -p /app/models/pycaret

EXPOSE 8083

CMD ["python", "server.py"]

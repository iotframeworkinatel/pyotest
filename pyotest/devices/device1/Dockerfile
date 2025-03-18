FROM ubuntu:22.04

# Atualiza e instala dependências essenciais
RUN apt-get update && apt-get install -y \
    qemu-system-arm \  # Emulador de ARM
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Define o diretório de trabalho
WORKDIR /app

# Copia os arquivos necessários para o container
COPY 50.0.0.3-r3.bin /firmware/50.0.0.3-r3.bin
COPY app.py /app/app.py

# Instala dependências do Flask
RUN pip3 install flask

# Expor a porta usada pelo Flask
EXPOSE 5000

# Comando de entrada
CMD ["python3", "/app/app.py"]

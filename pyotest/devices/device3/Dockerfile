FROM ubuntu:22.04

# Instalar dependências para simulação de firmware
RUN apt-get update && apt-get install -y qemu-system-arm python3 python3-pip

# Copiar o firmware para dentro do container
COPY firmware_v1.bin /firmware/

# Copiar a aplicação que simula o dispositivo
COPY app.py /app.py

# Definir ponto de entrada (simulação do dispositivo)
CMD ["python3", "/app.py"]

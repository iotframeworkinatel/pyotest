import os
import subprocess
import time
import threading
from flask import Flask, jsonify

# Caminho para o firmware binário
FIRMWARE_PATH = "/firmware/50.0.0.3-r3.bin"

# Função para rodar o firmware no QEMU
def run_firmware():
    cmd = [
        "qemu-system-arm",
        "-M", "versatilepb",  # Emulação de uma placa ARM genérica
        "-cpu", "arm926",
        "-kernel", FIRMWARE_PATH,
        "-nographic"
    ]
    subprocess.run(cmd)

# Iniciar firmware em uma thread separada para não travar o Flask
firmware_thread = threading.Thread(target=run_firmware, daemon=True)
firmware_thread.start()

# Criar API para monitoramento
app = Flask(__name__)

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"status": "running", "firmware": "v1"})

@app.route('/restart', methods=['POST'])
def restart():
    global firmware_thread
    if firmware_thread.is_alive():
        return jsonify({"message": "Firmware já em execução"}), 400

    firmware_thread = threading.Thread(target=run_firmware, daemon=True)
    firmware_thread.start()
    return jsonify({"message": "Firmware reiniciado"}), 200

if __name__ == "__main__":
    # Espera um pouco para garantir que o firmware esteja rodando antes de iniciar o Flask
    time.sleep(5)
    app.run(host="0.0.0.0", port=5000)

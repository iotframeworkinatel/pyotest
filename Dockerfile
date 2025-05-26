# Usar uma imagem base oficial do Python
FROM python:3.10-slim

# Adiciona um usuário não-root
RUN useradd -m pyotestuser

# Definir o diretório de trabalho dentro do contêiner
WORKDIR /app

# Copiar o arquivo de requisitos para o contêiner
COPY requirements.txt .

# Instalar as dependências necessárias
RUN pip install --no-cache-dir -r requirements.txt

# Instalar nmap
RUN apt-get update && apt-get install -y nmap

# Copiar todo o código da aplicação para o contêiner
COPY . .

# Troca para o usuário não-root
USER pyotestuser

# Comando padrão para executar os testes
CMD ["python3", ".", "-n", "172.20.0.0/27", "--test", "-o", "html"]

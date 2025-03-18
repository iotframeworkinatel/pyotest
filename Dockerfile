# Usar uma imagem base oficial do Python
FROM python:3.10-slim

# Definir o diretório de trabalho dentro do contêiner
WORKDIR /app

# Copiar o arquivo de requisitos para o contêiner
COPY requirements.txt .

# Instalar as dependências necessárias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo o código da aplicação para o contêiner
COPY . .

# Comando padrão para executar os testes
CMD ["pytest", "--disable-warnings"]

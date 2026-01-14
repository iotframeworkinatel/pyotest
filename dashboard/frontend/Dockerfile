FROM node:18-bullseye

# Define diretório de trabalho
WORKDIR /app

# Copia dependências e instala
COPY package*.json ./
RUN npm install

# Copia o resto dos arquivos do projeto
COPY . .

# Garante que o Tailwind tenha config (sem erro de shell)
RUN [ ! -f "tailwind.config.js" ] && npx tailwindcss init -p || echo "Tailwind config exists"

# Faz o build de produção do app React/Vite
RUN npm run build

# Muda o diretório de trabalho para a pasta buildada
WORKDIR /app/dist

ENV VITE_API_URL=http://localhost:8000


# Expõe a porta padrão do Vite Preview
EXPOSE 5173

# Roda o preview (servidor de produção do Vite)
CMD ["npm", "run", "dev", "--", "--host", "--port", "5173"]

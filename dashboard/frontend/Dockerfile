# Etapa 1: Build do Vite/React
FROM node:18-bullseye AS builder

WORKDIR /app

# Copia configs e instala dependências
COPY package*.json ./
RUN npm install --include=dev

# Copia o resto dos arquivos
COPY . .

# Executa o build
RUN npm run build

# Etapa 2: Servir com Nginx
FROM nginx:stable-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

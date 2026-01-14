# Etapa de build
FROM node:18-bullseye AS build

WORKDIR /app
COPY package*.json ./
RUN npm install && npm install -D vite @vitejs/plugin-react tailwindcss postcss autoprefixer

COPY . .
RUN npm run build

# Etapa final: servidor Nginx
FROM nginx:stable-alpine

COPY --from=build /app/dist /usr/share/nginx/html

RUN rm /etc/nginx/conf.d/default.conf
RUN echo 'server { \
  listen 80; \
  server_name localhost; \
  root /usr/share/nginx/html; \
  index index.html; \
  location / { \
    try_files $uri /index.html; \
  } \
}' > /etc/nginx/conf.d/dashboard.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

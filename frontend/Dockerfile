# 这个 Dockerfile 负责构建 Vue 前端静态资源，并交给 Nginx 对外提供访问。
FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_API_BASE_URL=http://127.0.0.1:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

FROM node:22-alpine AS build

WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

FROM nginx:stable-alpine
ENV NGINX_ENVSUBST_FILTER=^API_UPSTREAM$
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80

FROM node:25-alpine AS build

WORKDIR /app
# Default empty = same-origin /v1 via nginx (prod/on-prem). Dev compose may override.
ARG VITE_API_BASE=
ENV VITE_API_BASE=$VITE_API_BASE
COPY package.json ./
RUN npm install --no-audit --no-fund --loglevel=warn --maxsockets=3
COPY . .
RUN npm run build

FROM nginx:alpine
ARG NGINX_CONF=nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY ${NGINX_CONF} /etc/nginx/conf.d/default.conf
EXPOSE 80

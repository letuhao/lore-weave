FROM node:25-alpine AS build

WORKDIR /app
ARG VITE_API_BASE=http://localhost:3000
ENV VITE_API_BASE=$VITE_API_BASE
COPY package.json ./
RUN npm config set strict-ssl false && \
    npm install --no-audit --no-fund --loglevel=warn --maxsockets=3
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

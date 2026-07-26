FROM node:25-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm config set strict-ssl false && \
    npm install --no-audit --no-fund --loglevel=warn --maxsockets=3
COPY . .
RUN npm run build

FROM node:25-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json ./
RUN npm config set strict-ssl false && \
    npm install --no-audit --no-fund --loglevel=warn --omit=dev --maxsockets=3
COPY --from=build /app/dist ./dist
EXPOSE 3000
CMD ["node", "dist/main.js"]

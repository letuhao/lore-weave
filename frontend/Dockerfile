FROM node:25-alpine AS build

WORKDIR /app
ARG VITE_API_BASE=http://localhost:3000
ENV VITE_API_BASE=$VITE_API_BASE
# 🔴 `npm ci` FROM A COMMITTED LOCKFILE, changed 2026-09-13 (#254).
#
# This copied `package.json` alone and ran `npm install`, while `frontend/package-lock.json` was
# gitignored — so the image resolved all 74 floating ranges FRESH at build time. Two builds of the
# same commit could produce different dependency trees, which makes "we upgraded react-router" a
# statement about one machine at one moment rather than about the release.
#
# That is not untidiness, it undoes the fix: a vulnerable transitive dependency can re-enter on the
# next build with no commit to blame. The same shape as `minio/minio:latest` in this very release,
# where an unpinned reference turned a green pipeline red with nothing in the diff.
#
# `npm ci` also FAILS CLOSED when the lock and the manifest disagree, which is the behaviour worth
# having: drift becomes a build error instead of a silent re-resolution.
COPY package.json package-lock.json ./
RUN npm config set strict-ssl false && \
    npm ci --no-audit --no-fund --loglevel=warn --maxsockets=3
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

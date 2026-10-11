# Build context is the repo root (see docker-compose.yml) so the shared stylesheet can be bundled
FROM node:20-alpine AS build
WORKDIR /src/pure-spa/frontend
COPY pure-spa/frontend/package.json pure-spa/frontend/package-lock.json ./
RUN npm ci
COPY shared/static /src/shared/static
COPY pure-spa/frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY pure-spa/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/pure-spa/frontend/dist /usr/share/nginx/html

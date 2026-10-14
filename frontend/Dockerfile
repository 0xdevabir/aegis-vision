# syntax=docker/dockerfile:1
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Empty = no demo button. Set through DEMO_LOGIN_* in .env (docker-compose.yml).
ARG VITE_DEMO_USERNAME=""
ARG VITE_DEMO_PASSWORD=""
RUN VITE_DEMO_USERNAME="$VITE_DEMO_USERNAME" VITE_DEMO_PASSWORD="$VITE_DEMO_PASSWORD" npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

# Frontend Dockerfile — build dist, serve via nginx
FROM node:20-alpine AS builder

WORKDIR /build
COPY package.json pnpm-lock.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile || npm install

COPY . .
RUN pnpm build || npm run build

# ─── Runtime ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80 443

# Frontend Dockerfile — build dist, serve via nginx
# 用法: docker build --build-arg NGINX_CONF=nginx-kbkkk.conf -t ai-trader-frontend:kbkkk .
# 默认 nginx.conf 是 dyddd-prod 用 (HTTPS)
# kbkkk-prod 用 nginx-kbkkk.conf (纯 HTTP)
FROM node:20-alpine AS builder

WORKDIR /build
COPY package.json pnpm-lock.yaml* ./
# pnpm 12+ 默认禁止自动跑依赖的 build script (ERR_PNPM_IGNORED_BUILDS)
# 但 esbuild 等二进制包必须 build 才会装上 native binary
# 解法：用 --allow-build esbuild 显式授权，让 esbuild 的 build script 跑起来
RUN corepack enable \
    && pnpm install --frozen-lockfile --allow-build esbuild \
    || (echo "pnpm install failed, fallback npm:" && npm install --no-audit --no-fund)

COPY . .
RUN pnpm build || npm run build

# ─── Runtime ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

ARG NGINX_CONF=nginx.conf
COPY --from=builder /build/dist /usr/share/nginx/html
COPY ${NGINX_CONF} /etc/nginx/conf.d/default.conf

EXPOSE 80 443

# syntax=docker/dockerfile:1.6
# Multi-stage build: install + vite build → nginx-served static bundle.
ARG NODE_VERSION=20

# ─── Builder ────────────────────────────────────────────────────────────────
FROM node:${NODE_VERSION}-alpine AS builder

ENV CI=true \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false

WORKDIR /app

# Cache npm install separately from the source copy for fast rebuilds.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund --prefer-offline

COPY . .

# Build-time env vars baked into the static bundle. Provide via
# --build-arg in CI; absent values become empty strings.
ARG VITE_API_URL=
ARG VITE_KAKAO_MAP_KEY=
ENV VITE_API_URL=$VITE_API_URL \
    VITE_KAKAO_MAP_KEY=$VITE_KAKAO_MAP_KEY

RUN npm run build

# ─── Runtime (nginx) ────────────────────────────────────────────────────────
FROM nginx:1.29-alpine AS runtime

# nginx in non-root mode listens on 8080 (privileged ports require root).
RUN apk add --no-cache curl tini \
    && rm -rf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Pre-create cache + run dirs that nginx needs at start so we can drop
# privileges to the built-in `nginx` user.
RUN mkdir -p /var/cache/nginx /var/run \
    && chown -R nginx:nginx /var/cache/nginx /var/run /usr/share/nginx/html /etc/nginx/conf.d \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --spider -q http://localhost:8080/healthz || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["nginx", "-g", "daemon off;"]

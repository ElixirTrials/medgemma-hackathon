# Multi-stage build: Node for building, Nginx for serving
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies first (layer caching)
COPY apps/hitl-ui/package.json apps/hitl-ui/package-lock.json* ./
RUN npm ci

# Copy source and build
COPY apps/hitl-ui/ ./
RUN npm run build

# --- Production stage ---
FROM nginx:alpine

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Nginx config: SPA routing + port 3000
COPY apps/hitl-ui/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]

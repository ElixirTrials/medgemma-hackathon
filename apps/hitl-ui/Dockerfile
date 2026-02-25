# Multi-stage build: Node for building, Nginx for serving
FROM node:20-alpine AS build

WORKDIR /app

# Build-time API URL and base path (for Cloud Run, set VITE_API_URL to your API service URL)
ARG VITE_API_URL=http://localhost:8000
ARG BASE_PATH=/
ENV VITE_API_URL=$VITE_API_URL
ENV BASE_PATH=$BASE_PATH

# Install dependencies first (layer caching)
COPY apps/hitl-ui/package.json apps/hitl-ui/package-lock.json* ./
RUN npm ci

# Copy source and build (Vite outDir is "build" per vite.config.ts)
COPY apps/hitl-ui/ ./
RUN npm run build

# --- Production stage ---
FROM nginx:alpine

# Copy built assets (vite.config outDir is "build")
COPY --from=build /app/build /usr/share/nginx/html

# Nginx config: SPA routing; listen 8080 for Cloud Run default PORT
COPY apps/hitl-ui/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]

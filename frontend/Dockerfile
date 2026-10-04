FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-slim AS builder
WORKDIR /app
# NEXT_PUBLIC_* vars are inlined into the client bundle at build time, not
# read at container start — so this must be a build arg, not just a runtime
# `environment:` entry in docker-compose.yml (which only affects the server
# process, e.g. the BACKEND_URL used by the API routes).
ARG NEXT_PUBLIC_ROSBRIDGE_URL=ws://localhost:9090
ENV NEXT_PUBLIC_ROSBRIDGE_URL=$NEXT_PUBLIC_ROSBRIDGE_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Standalone output (next.config.mjs: output: "standalone") only needs the
# traced server bundle + static assets, not node_modules or the source tree.
FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]

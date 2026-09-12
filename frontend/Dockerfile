FROM node:22-alpine AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY frontend/ ./
ARG NEXT_PUBLIC_GO_API_URL=http://127.0.0.1:8787
ARG NEXT_PUBLIC_GO_WS_URL=ws://127.0.0.1:8787/ws
ARG NEXT_PUBLIC_PYTHON_API_URL=http://127.0.0.1:8001
ARG NEXT_PUBLIC_PYTHON_WS_URL=ws://127.0.0.1:8001/ws
ENV NEXT_PUBLIC_GO_API_URL=$NEXT_PUBLIC_GO_API_URL
ENV NEXT_PUBLIC_GO_WS_URL=$NEXT_PUBLIC_GO_WS_URL
ENV NEXT_PUBLIC_PYTHON_API_URL=$NEXT_PUBLIC_PYTHON_API_URL
ENV NEXT_PUBLIC_PYTHON_WS_URL=$NEXT_PUBLIC_PYTHON_WS_URL
RUN npm run build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
WORKDIR /app
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=build --chown=nextjs:nodejs /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 CMD node -e "fetch('http://127.0.0.1:3000').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
CMD ["node", "server.js"]

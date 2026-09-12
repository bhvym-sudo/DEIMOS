FROM golang:1.23-bookworm AS build

RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY backend/go.mod backend/go.sum ./
RUN go mod download
COPY backend/ ./
RUN CGO_ENABLED=1 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/deimos ./cmd/deimos

FROM debian:bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /out/deimos /usr/local/bin/deimos
COPY config/ /app/config/
ENV DEIMOS_ROOT=/app
ENV DEIMOS_GO_ADDR=0.0.0.0:8787
EXPOSE 8787
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 CMD curl --fail --silent http://127.0.0.1:8787/api/health || exit 1
CMD ["deimos"]

FROM golang:1.25-alpine AS builder
WORKDIR /src
COPY phobos-twitter/go.mod phobos-twitter/go.sum ./
RUN go mod download
COPY phobos-twitter/backend ./backend
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -o /out/phobos-tweeter ./backend/cmd/trex

FROM mcr.microsoft.com/playwright/python:v1.55.0-noble
RUN pip install --no-cache-dir playwright==1.55.0
WORKDIR /data
COPY --from=builder /out/phobos-tweeter /usr/local/bin/phobos-tweeter
COPY phobos-twitter/python_worker /opt/phobos-twitter/python_worker
ENV TREX_PYTHON_WORKER=/opt/phobos-twitter/python_worker/search_timeline.py
ENV TREX_ACCOUNT_WORKER=/opt/phobos-twitter/python_worker/account_lookup.py
ENV TREX_SESSION_RUNTIME=/data/sessions/x_session.json
EXPOSE 8790
CMD ["phobos-tweeter"]

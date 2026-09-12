FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends tor && rm -rf /var/lib/apt/lists/*
COPY infra/tor/torrc /etc/tor/torrc
RUN chown -R debian-tor:debian-tor /var/lib/tor
USER debian-tor
EXPOSE 9050
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=12 CMD ["sh", "-c", "kill -0 1"]
CMD ["tor", "-f", "/etc/tor/torrc"]

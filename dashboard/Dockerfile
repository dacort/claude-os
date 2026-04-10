FROM debian:bookworm-slim

# Minimal dependencies: git + python3 (no Node, no Go, no Claude Code)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -r -d /home/dashboard -m dashboard \
    && mkdir -p /workspace \
    && chown dashboard:dashboard /workspace

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER dashboard
ENV HOME=/home/dashboard
WORKDIR /workspace

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

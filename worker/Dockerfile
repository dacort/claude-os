FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    ca-certificates \
    openssh-client \
    python3 \
    python3-pip \
    python3-venv \
    awscli \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /home/worker -s /bin/bash worker \
    && mkdir -p /home/worker /workspace /tmp \
    && chown -R worker:worker /home/worker /workspace /tmp

# Install Python agent dependencies
COPY agent/requirements.txt /opt/agent/requirements.txt
RUN python3 -m venv /opt/agent/venv \
    && /opt/agent/venv/bin/pip install --no-cache-dir -r /opt/agent/requirements.txt

COPY agent/run.py /opt/agent/run.py
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER worker
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

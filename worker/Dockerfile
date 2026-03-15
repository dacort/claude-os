FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    ca-certificates \
    openssh-client \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for Claude Code CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install CLI tools (Claude Code, Codex, Gemini)
RUN npm install -g @anthropic-ai/claude-code @openai/codex @google/gemini-cli

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh && rm -rf /var/lib/apt/lists/*

# Install Go 1.25 from official binary tarball (multi-arch)
RUN ARCH=$(dpkg --print-architecture) \
    && curl -fsSL "https://go.dev/dl/go1.25.0.linux-${ARCH}.tar.gz" -o /tmp/go.tar.gz \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /home/worker -s /bin/bash worker \
    && mkdir -p /home/worker/.claude /home/worker/.codex /home/worker/go /workspace /tmp \
    && chown -R worker:worker /home/worker /workspace /tmp

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER worker
ENV HOME=/home/worker \
    GOPATH=/home/worker/go \
    PATH=/usr/local/go/bin:/home/worker/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

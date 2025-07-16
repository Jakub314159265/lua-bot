FROM python:3.12-slim

# Add labels for better Podman integration
LABEL maintainer="lua-bot"
LABEL description="Secure Lua code execution environment"
LABEL version="1.0"

# Install dependencies
RUN pip install --no-cache-dir lupa

# Create non-root user with explicit UID/GID for better Podman compatibility
RUN groupadd -g 1000 botuser && \
    useradd -m -u 1000 -g 1000 botuser

WORKDIR /home/botuser/
COPY --chown=botuser:botuser run_lua.py .

RUN chmod 755 /home/botuser/run_lua.py

USER botuser

ENTRYPOINT ["python", "run_lua.py"]

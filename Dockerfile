FROM python:3.12-slim

# Install dependencies
RUN pip install lupa

# Create non-root user
RUN useradd -m -u 1000 botuser

WORKDIR /home/botuser/
COPY --chown=botuser:botuser run_lua.py .

USER botuser

ENTRYPOINT ["python", "run_lua.py"]

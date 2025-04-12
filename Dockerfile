FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

COPY pyproject.toml .
RUN uv pip install -r pyproject.toml --system --group prod

COPY . .
RUN chmod +x deploy/entrypoint.sh && \
    uv run tool/generate_deploy_env.py --env-file .env --override-file deploy/.env.override --output-file deploy/.env && \
    rm .env && \
    mv deploy/.env .

ENTRYPOINT [ "/bin/bash", "-c", "/app/deploy/entrypoint.sh" ]
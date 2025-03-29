FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

COPY pyproject.toml .
RUN uv pip install -r pyproject.toml

COPY . .

CMD ["python", "app/main.py"]

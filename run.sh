#!/bin/bash

if [ "$1" = "-c" ]; then
    echo "[*] Starting Docker Compose stack..."
    docker-compose --env-file .env up --build
else
    echo "[*] Loading .env and running locally..."
    LOG_DIR="$(dirname "$0")/_logs"
    uv run tool/launch.py --log-dir "$LOG_DIR"
fi

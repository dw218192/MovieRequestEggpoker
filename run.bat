@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

IF "%1"=="-c" (
    echo [*] Starting Docker Compose stack...
    docker-compose --env-file .env up --build
) ELSE (
    echo [*] Loading .env and running locally...
    SET LOG_DIR=%~dp0_logs
    uv run tool/launch.py --log-dir "!LOG_DIR!" %*
)

ENDLOCAL

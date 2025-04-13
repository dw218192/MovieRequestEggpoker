@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

SET LOG_DIR=%~dp0_logs
uv run tool/launch.py --log-dir "!LOG_DIR!" --storage-config "deploy/windows/storage_config.json" %*

ENDLOCAL

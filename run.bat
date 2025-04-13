@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

uv run tool/launch.py --storage-config "deploy/windows/storage_config.json" %*

ENDLOCAL

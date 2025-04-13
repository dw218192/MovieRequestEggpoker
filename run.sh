#!/bin/bash

LOG_DIR="$(dirname "$0")/_logs"
uv run tool/launch.py --log-dir "$LOG_DIR" --storage-config "deploy/linux/storage_config.json" "$@"
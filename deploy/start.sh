#!/bin/bash
_script_dir=$(dirname $0)
_root_dir=$(realpath $_script_dir/..)
docker compose -f $_root_dir/docker-compose.yml up -d --build
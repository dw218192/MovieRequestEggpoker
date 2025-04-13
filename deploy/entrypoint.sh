#!/bin/bash
_script_dir=$(dirname $0)
_root_dir=$(realpath $_script_dir/..)
_log_dir=$_root_dir/_logs

mkdir -p $_log_dir

uv run gunicorn -c $_root_dir/tool/gunicorn.conf.py 'app.main:init_app()'
import os
import multiprocessing
from dotenv import load_dotenv

load_dotenv()

port = os.getenv("MOVIE_REQUEST_SERVER_PORT", "8000")
bind = f"0.0.0.0:{port}"

# Worker settings
workers = 1
worker_class = "sync"
threads = 2
timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

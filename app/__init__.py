import logging, logging.config
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

g_log_level = os.getenv("MOVIE_REQUEST_SERVER_LOG_LEVEL", "INFO").upper()
g_log_file_name = os.getenv("MOVIE_REQUEST_SERVER_LOG_FILE", "_logs/app.log")

g_logging_config = {
    "version": 1,
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "filename": g_log_file_name,
            "maxBytes": 10485760,  # 10MB
            "backupCount": 2,
        }
    },
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        }
    },
    "loggers": {
        "root": {
            "handlers": ["file"],
            "level": "WARNING",
        },
        __package__: {
            "handlers": ["file"],
            "level": g_log_level,
            "propagate": False,
        },
    },
}

logging.config.dictConfig(g_logging_config)

logger = logging.getLogger(__package__)
logger.info(f"Logger initialized with level: {g_log_level}")

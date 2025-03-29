import logging, logging.config
import os
import sys

from dotenv import load_dotenv

load_dotenv()

g_log_level = os.getenv("MOVIE_REQUEST_SERVER_LOG_LEVEL", "INFO").upper()
g_logging_config = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        }
    },
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        }
    },
    'loggers': {
        'root': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
        __package__: {
            'handlers': ['console'],
            'level': g_log_level,
            'propagate': False,
        },
    }
}

logging.config.dictConfig(g_logging_config)

logger = logging.getLogger(__package__)
logger.info(f"Logger initialized with level: {g_log_level}")
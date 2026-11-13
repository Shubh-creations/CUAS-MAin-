"""
Structured Logging Module for CUAS Defense Platform.
Provides military-grade timestamped logging with ANSI coloring and file persistence.
"""

import logging
import os
import sys
from datetime import datetime

class MilitaryFormatter(logging.Formatter):
    GREY = "\x1b[38;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    CYAN = "\x1b[36;20m"
    RESET = "\x1b[0m"

    FORMAT_PREFIX = "[%(asctime)s.%(msecs)03d] [%(levelname)-8s] [%(name)s] "
    FORMAT_SUFFIX = "%(message)s"

    FORMATS = {
        logging.DEBUG: GREY + FORMAT_PREFIX + RESET + FORMAT_SUFFIX,
        logging.INFO: GREEN + FORMAT_PREFIX + RESET + FORMAT_SUFFIX,
        logging.WARNING: YELLOW + FORMAT_PREFIX + RESET + FORMAT_SUFFIX,
        logging.ERROR: RED + FORMAT_PREFIX + RESET + FORMAT_SUFFIX,
        logging.CRITICAL: BOLD_RED + FORMAT_PREFIX + RESET + FORMAT_SUFFIX,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.FORMAT_PREFIX + self.FORMAT_SUFFIX)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def get_logger(name: str = "CUAS", log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(MilitaryFormatter())
    logger.addHandler(console_handler)

    # File Handler
    try:
        os.makedirs(log_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        file_path = os.path.join(log_dir, f"cuas_{date_str}.log")
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_fmt = logging.Formatter(
            "[%(asctime)s.%(msecs)03d] [%(levelname)-8s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Failed to initialize file logger: {e}")

    logger.propagate = False
    return logger

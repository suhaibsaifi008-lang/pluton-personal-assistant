"""
Activity log — every command Pluton hears and every significant action it
takes gets written here, timestamped. This is the transparency layer from
the spec: you should always be able to see what Pluton did and when.
"""

import logging
import os

import config


def get_logger():
    log_dir = os.path.expandvars(config.LOG_FOLDER)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "activity.log")

    logger = logging.getLogger("pluton")
    if not logger.handlers:  # avoid duplicate handlers if called more than once
        logger.setLevel(logging.INFO)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("[log] %(message)s"))
        logger.addHandler(console_handler)

    return logger

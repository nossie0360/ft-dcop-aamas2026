import logging
import pathlib


def configure_logger(
    logger_name: str,
    log_path: pathlib.Path,
    level=logging.INFO,
    to_file: bool=True,
    stdout: bool=False
):
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.setLevel(level)

    if to_file:
        ch = logging.FileHandler(log_path)
        ch.setLevel(level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    if stdout:
        ch_stdout = logging.StreamHandler()
        ch_stdout.setLevel(level)
        formatter_stdout = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        ch_stdout.setFormatter(formatter_stdout)
        logger.addHandler(ch_stdout)


def log_level(level_str: str) -> int:
    level_str = level_str.lower()
    if level_str == "critical":
        return logging.CRITICAL
    elif level_str == "error":
        return logging.ERROR
    elif level_str == "warning":
        return logging.WARNING
    elif level_str == "info":
        return logging.INFO
    elif level_str == "debug":
        return logging.DEBUG
    else:
        raise ValueError("Invalid log level.")

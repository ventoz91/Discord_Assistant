import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging():
    log_level = getattr(logging, os.getenv("LOG_LEVEL", "WARNING").upper(), logging.WARNING)
    root = logging.getLogger("bot")
    root.setLevel(logging.DEBUG)
    if root.handlers:
        return
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    os.makedirs("data", exist_ok=True)
    fh = RotatingFileHandler(
        "data/bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(log_level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

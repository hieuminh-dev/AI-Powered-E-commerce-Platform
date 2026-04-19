import logging
import sys
from logging.handlers import RotatingFileHandler
import os


def setup_logging(app):
    """Setup application logging"""

    if not os.path.exists("logs"):
        os.makedirs("logs")

    if app.config.get("DEBUG"):
        logging_level = logging.DEBUG
    else:
        logging_level = logging.INFO

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        "logs/ecommerce_chatbot.log", maxBytes=10240000, backupCount=10, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging_level)

    # Ensure Windows console can print UTF-8 logs safely without wrapping/closing stdout.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    # Keep original stdout stream. Wrapping sys.stdout.buffer with TextIOWrapper can
    # close the underlying stream unexpectedly on Windows and crash Flask/Click.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging_level)

    # Avoid duplicate logs when app initialization runs multiple times.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    app.logger.setLevel(logging_level)
    app.logger.handlers = []
    app.logger.propagate = True

    loggers = [
        "services.chat_service",
        "services.vector_service",
        "services.product_service",
        "services.auth_service",
        "routes.auth_routes",
        "routes.product_routes",
        "routes.chat_routes",
    ]

    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging_level)
        logger.handlers = []
        logger.propagate = True

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    app.logger.info("Logging configured successfully")

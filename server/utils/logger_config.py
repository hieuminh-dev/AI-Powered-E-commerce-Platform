import logging
import sys
from logging.handlers import RotatingFileHandler
import os


def setup_logging(app):

    if not os.path.exists("logs"):
        os.makedirs("logs")

    if app.config.get("DEBUG"):
        logging_level = logging.DEBUG
    else:
        logging_level = logging.INFO

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        "logs/ecommerce_chatbot.log", maxBytes=10240000, backupCount=10
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    app.logger.setLevel(logging_level)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)

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
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    app.logger.info("Logging configured successfully")

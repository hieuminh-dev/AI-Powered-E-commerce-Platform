#!/usr/bin/env python3

import os
import socket
from app import create_app


def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _resolve_port(host: str, requested_port: int, max_attempts: int = 20) -> int:
    for port in range(requested_port, requested_port + max_attempts):
        if _is_port_available(host, port):
            return port
    raise RuntimeError(
        f"No available port found in range {requested_port}-{requested_port + max_attempts - 1}"
    )


def main():
    config_name = os.environ.get("FLASK_ENV", "development")
    # Default to 5001 to avoid common conflicts with Docker/WSL on 5000.
    requested_port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0")

    app = create_app(config_name)
    resolved_port = _resolve_port(host, requested_port)

    if resolved_port != requested_port:
        app.logger.warning(
            "Requested port %s is in use, switching to %s",
            requested_port,
            resolved_port,
        )
    else:
        app.logger.info("Using port %s", resolved_port)

    if config_name == "development":
        # Keep single-process dev server for stable debugging/logging.
        app.run(
            host=host,
            port=resolved_port,
            debug=True,
            threaded=True,
            use_reloader=False,
        )
    else:
        app.run(host=host, port=resolved_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()

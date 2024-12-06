# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""Main module to run the prometheus exporter server."""

import argparse
import logging
import os
import sys
from wsgiref.simple_server import make_server

from prometheus_client import make_wsgi_app
from prometheus_client.core import REGISTRY

from src.collector import Config, DashBoardsCollector


def setup_logging() -> None:
    """Setup the log for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )


def parse_command_line(args: list[str]) -> argparse.Namespace:
    """Command line parser.

    Args:
        args (list[str]): List of arguments to parse

    Returns:
        argparse.Namespace: Command line arguments.
    """
    parser = argparse.ArgumentParser(
        prog=__package__,
        description=__doc__,
    )
    parser.add_argument(
        "url",
        type=str,
        help="The OpenSearch address to fetch metrics from. E.g: http(s)://<IP>:5601",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9684,
        help="The port number to the prometheus exporter to use (default: 9684)",
    )

    if len(args) == 0 or (len(args) == 1 and args[0] == "help"):
        parser.print_help()
        parser.exit()

    return parser.parse_args(args)


def main() -> None:
    """Enter the exporter application"""
    args = parse_command_line(sys.argv[1:])
    setup_logging()
    user = os.getenv("OPENSEARCH_DASHBOARDS_USER", "")
    password = os.getenv("OPENSEARCH_DASHBOARDS_PASSWORD", "")

    config = Config(args.url, user, password)
    REGISTRY.register(DashBoardsCollector(config))
    app = make_wsgi_app()
    httpd = make_server("", args.port, app)
    httpd.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()

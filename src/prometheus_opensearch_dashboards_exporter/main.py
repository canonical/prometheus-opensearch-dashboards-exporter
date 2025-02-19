# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""Main module to run the prometheus exporter server."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Iterable
from wsgiref.simple_server import make_server

from prometheus_client import make_wsgi_app
from prometheus_client.core import REGISTRY

from prometheus_opensearch_dashboards_exporter.collector import (
    Config,
    DashboardsCollector,
)

APP = make_wsgi_app()


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
        prog="prometheus-opensearch-dashboards-exporter",
        description="Prometheus Exporter for OpenSearch Dashboards",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:5601",
        help="The OpenSearch address to fetch metrics from. E.g: http(s)://<IP>:5601",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9684,
        help="The port number to the prometheus exporter to use (default: 9684)",
    )

    return parser.parse_args(args)


def metrics_app(environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
    """Create the WSGI app to respond at the /metrics path

    Args:
        environ (dict[str, Any]): environment variable defined by the WSGI specification.
        It contains the path part of the URL requested by the client
        start_response (Any): Function that is provided by the WSGI server
        and is used by the WSGI application to start the HTTP response

    Returns:
        Iterable[bytes]: Response of the request. In the case prometheus metrics at /metrics and
        404 Not found for other paths
    """
    path: str = environ.get("PATH_INFO", "")

    if path == "/metrics":
        return APP(environ, start_response)

    if path == "/":
        html_file_path = Path(__file__).parent / "index.html"
        if html_file_path.exists():
            start_response("200 OK", [("Content-Type", "text/html")])
            return [html_file_path.read_bytes()]

        start_response("500 Internal Error", [("Content-Type", "text/plain")])
        return [b"500 HTML Page Not Found"]

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"404 Not Found"]


def main() -> None:
    """Enter the exporter application"""
    args = parse_command_line(sys.argv[1:])
    setup_logging()
    user = os.getenv("OPENSEARCH_DASHBOARDS_USER", "")
    password = os.getenv("OPENSEARCH_DASHBOARDS_PASSWORD", "")

    config = Config(args.url, user, password)
    REGISTRY.register(DashboardsCollector(config))
    with make_server("", args.port, metrics_app) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()

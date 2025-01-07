# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src.collector import (
    API_STATUS_ENDPOINT,
    METRICS_PREFIX,
    Config,
    DashboardsCollector,
)


@pytest.fixture
def mock_opensearch_api_handler(api_response):
    class MockOpenSearchAPIHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == API_STATUS_ENDPOINT:
                response = api_response
            else:
                response = {"error": "Unknown endpoint"}

            self.send_response(200 if self.path == API_STATUS_ENDPOINT else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

    return MockOpenSearchAPIHandler


@pytest.fixture
def start_mock_server(mock_opensearch_api_handler):
    server = HTTPServer(("localhost", 5601), mock_opensearch_api_handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


@pytest.fixture
def prometheus_exporter(start_mock_server):
    # Start the Prometheus exporter
    process = subprocess.Popen(
        ["python3", "./src/main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Allow some time for the exporter to start
    time.sleep(2)
    yield process
    process.terminate()
    process.wait()


@pytest.fixture
def wrong_prometheus_exporter(start_mock_server):
    # Start a wrong Prometheus exporter that won't be able to query because of tls
    process = subprocess.Popen(
        ["python3", "./src/main.py", "--url", "https://localhost:5601"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Allow some time for the exporter to start
    time.sleep(2)
    yield process
    process.terminate()
    process.wait()


@pytest.fixture
def expected_metrics():
    metrics = DashboardsCollector(Config("", "", "")).metrics({"foo": "bar"})
    return {f"{METRICS_PREFIX}{metric[0]}" for metric in metrics}

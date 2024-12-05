# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""Fixtures for unit tests"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def api_response():
    current_dir = Path(__file__).parent
    json_file_path = current_dir / "dashboard_response.json"

    with open(json_file_path, "r") as f:
        data = json.load(f)

    return data


@pytest.fixture
def mock_gauge():
    with patch("src.collector.GaugeMetricFamily") as mock:
        mock.return_value = mock
        yield mock
